---
description: Plan for a unified KV-based versioned store replacing both RedisStore and VersionedRedisStore, using bahamut's key design patterns
date: 2026-03-15
tags: [permastore, store, kvrocks, redis, bahamut, versioning]
---

# Unified KV Store with Bahamut Key Patterns

## Scope

This plan covers only changes within the `nomenklatura` package. Zavod and other
consumers are out of scope — they will migrate to the new store in a separate effort.
The old `RedisStore` and `VersionedRedisStore` remain in the codebase alongside the
new `KVStore` so that existing callers continue to work.

## Goal

Add a new `KVStore` that:

1. Uses bahamut-style composite KV keys instead of Redis sets for statements
2. Supports dataset versioning (carries over all utility methods from `VersionedRedisStore`)
3. Uses late-binding canonicalization (from bahamut) — store under raw entity IDs, resolve at read time
4. Keeps the Redis/KVRocks wire protocol (no custom server needed)
5. Skips the locking mechanism for now
6. `update()` is a noop (kept for back-compat), `pop()` raises `NotImplementedError`
7. Release is explicit — the writer does **not** auto-release on `close()`

## Why

The current two Redis stores have complementary weaknesses:

- **`RedisStore`** uses `SADD`/`SUNION` for statement storage. Every statement for an entity goes into a single set key (`s:{canonical_id}`). This means: (a) canonicalization is baked in at write time — resolver changes require full re-ingest, (b) no versioning, (c) no prefix scans — Redis sets are unordered blobs, so you can't efficiently filter by dataset or schema.

- **`VersionedRedisStore`** adds versioning but doubles down on sets: `stmt:{dataset}:{version}:{entity_id}` is a set of packed statements. Same problems: no prefix scans, dataset filtering requires deserializing every statement, `SUNION` across many keys for merged entities is expensive, and `SSCAN` for full iteration is slower than ordered iteration.

Bahamut showed that composite KV keys with prefix scans are the right primitive for this workload. KVRocks supports `SCAN` by prefix but more importantly supports raw `GET`/`SET` with sorted key iteration — which is exactly what we need.

## Key Design

### Statement keys

```
d:{dataset}:{version}:s:{entity_id}:{ext}:{stmt_id}:{schema}:{property}
```

- **`d:{dataset}:{version}`** — version-scoped prefix, enables `deleteRange` (or `SCAN` + `DEL`) for version cleanup
- **`s:`** — statement marker (distinguishes from inverted index)
- **`{entity_id}`** — raw source entity ID (not canonical) — this is the core late-binding change
- **`{ext}`** — `x` for external, empty for internal
- **`{stmt_id}:{schema}:{property}`** — statement identity

Value: orjson-packed tuple matching LevelDB format:
```python
(value, lang, original_value, origin, first_seen, last_seen)
```

This is leaner than the current Redis pack format because dataset, entity_id, schema, prop, external, and stmt_id are all encoded in the key.

### Inverted index keys

```
d:{dataset}:{version}:i:{target_entity_id}:{source_entity_id}
```

Value: empty (`b""`)

Same as bahamut. Enables graph traversal: "which entities in this dataset+version reference entity X?"

### Entity marker keys

```
d:{dataset}:{version}:e:{entity_id}
```

Value: schema name (bytes)

Cheap existence check and full-entity-inventory scan without touching statement data. Also enables schema filtering during `entities()` iteration without deserializing statements.

### Version metadata

```
meta:versions:{dataset}:{version}  → release timestamp
meta:latest:{dataset}              → latest version string
```

Simple KV entries. No Redis lists or sets for version tracking.

## How Operations Map

### Write path (`KVWriter.add_statement`)

All string-to-bytes encoding is done inline with `.encode(E)` (where `E` is
`rigour.env.ENCODING`, i.e. `"utf-8"`). No `b()` helper — matches `level.py`'s
performance-sensitive style.

```python
def add_statement(self, stmt: Statement) -> None:
    # Store under RAW entity_id, not canonical
    entity_id = stmt.entity_id
    ext = "x" if stmt.external else ""
    key = f"d:{self.ds_ver}:s:{entity_id}:{ext}:{stmt.id}:{stmt.schema}:{stmt.prop}".encode(E)
    value = orjson.dumps((stmt.value, stmt.lang or 0, stmt.original_value or 0,
                          stmt.origin or 0, stmt.first_seen, stmt.last_seen))
    self.pipeline.set(key, value)

    # Entity marker
    self.pipeline.set(f"d:{self.ds_ver}:e:{entity_id}".encode(E), stmt.schema.encode(E))

    # Inverted index for entity-typed properties
    if get_prop_type(stmt.schema, stmt.prop) == registry.entity.name:
        self.pipeline.set(f"d:{self.ds_ver}:i:{stmt.value}:{entity_id}".encode(E), b"")
```

`self.ds_ver` is `f"{dataset.name}:{version}"`, precomputed once in `__init__`.
No linker involved at write time. This is the key architectural shift.

### Point lookup (`KVView.get_entity`)

```python
def get_entity(self, id: str) -> Optional[SE]:
    # Late-binding: find all source IDs in this canonical's cluster
    source_ids = self.store.linker.connected(Identifier.get(id))

    statements = []
    for source_id in source_ids:
        for dataset, version in self.vers:
            prefix = f"d:{dataset}:{version}:s:{source_id}:"
            for key, value in self._prefix_scan(prefix):
                parts = key.split(":")
                ext = parts[5]
                if ext == "x" and not self.external:
                    continue
                stmt = _unpack_from_kv(parts, value, canonical_id=id)
                statements.append(stmt)

    return self.store.assemble(statements)
```

For unmerged entities (the vast majority), `connected()` returns just the entity itself — one prefix scan per dataset+version in scope. For merged entities, one scan per source ID per dataset+version.

### Full iteration (`KVView.entities`)

This is the hardest operation under late binding (see permastore.md "full-scan problem"). We use **approach 4: scattered reads from entity inventory** — which works well because most entities are unmerged singletons.

```python
def entities(self, include_schemata=None) -> Generator[SE, None, None]:
    seen: Set[str] = set()

    for dataset, version in self.vers:
        marker_prefix = f"d:{dataset}:{version}:e:"
        for key, schema_bytes in self._prefix_scan(marker_prefix):
            entity_id = key.split(":")[4]  # raw source ID

            # Schema pre-filter before hitting statements
            if include_schemata is not None:
                schema = model.get(schema_bytes.decode())
                if schema is not None and schema not in include_schemata:
                    continue

            # Canonicalize
            canonical_id = self.store.linker.get_canonical(entity_id)

            # Dedup merged entities
            if canonical_id in seen:
                continue
            # Only track IDs that differ from source (merged)
            if canonical_id != entity_id:
                seen.add(canonical_id)

            entity = self.get_entity(canonical_id)
            if entity is not None:
                # Re-check schema after assembly (merge may change it)
                if include_schemata is not None and entity.schema not in include_schemata:
                    continue
                yield entity
```

The `seen` set only grows for merged entities, not singletons. For the core dataset (~4M entities, ~591K canonical clusters), `seen` holds at most ~591K strings — tens of MB. For enrichment (150M entities, mostly unmerged), `seen` stays small.

The entity marker prefix scan is sequential and fast. For each entity, `get_entity` does one prefix scan per source ID per dataset+version — for singletons that's just one scan at a nearby key position.

**Schema pre-filtering** is a bonus from the entity marker: we can skip entities of the wrong schema without touching their statements at all. The current LevelDB store can only do this mid-iteration.

### Version management

```python
class KVStore:
    def release_version(self, dataset: str, version: str) -> None:
        self.db.set(f"meta:versions:{dataset}:{version}".encode(E), str(time.time()).encode(E))
        self.db.set(f"meta:latest:{dataset}".encode(E), version.encode(E))

    def get_latest(self, dataset: str) -> Optional[str]:
        val = self.db.get(f"meta:latest:{dataset}".encode(E))
        return val.decode(E) if val else None

    def get_history(self, dataset: str) -> List[str]:
        """List all versions of a dataset by scanning meta:versions:{dataset}:* keys."""
        prefix = f"meta:versions:{dataset}:"
        versions = []
        for key in self.db.scan_iter(match=f"{prefix}*".encode(E)):
            version = key.decode(E).split(":")[-1]
            versions.append(version)
        return sorted(versions, reverse=True)

    def has_version(self, dataset: str, version: str) -> bool:
        return self.db.exists(f"meta:versions:{dataset}:{version}".encode(E)) > 0

    def drop_version(self, dataset: str, version: str) -> None:
        # Scan and delete all keys with this dataset+version prefix
        prefix = f"d:{dataset}:{version}:"
        pipeline = self.db.pipeline()
        cmds = 0
        for key in self.db.scan_iter(match=f"{prefix}*".encode(E)):
            pipeline.delete(key)
            cmds += 1
            if cmds > 1_000:
                pipeline.execute()
                pipeline = self.db.pipeline()
                cmds = 0
        if cmds > 0:
            pipeline.execute()
        self.db.delete(f"meta:versions:{dataset}:{version}".encode(E))
        # Update latest pointer if this was the latest
        latest = self.get_latest(dataset)
        if latest == version:
            history = self.get_history(dataset)
            if history:
                self.db.set(f"meta:latest:{dataset}".encode(E), history[0].encode(E))
            else:
                self.db.delete(f"meta:latest:{dataset}".encode(E))
```

Release is **always explicit** — the caller must call `store.release_version()` or
`writer.release()` after writing is complete. The writer's `close()` flushes the
batch but does not release. This avoids exposing partially-written data.

```python
class KVWriter:
    def release(self) -> None:
        self.store.release_version(self.dataset.name, self.version)

    def close(self) -> None:
        self.flush()
        # Does NOT release — caller must call release() explicitly
```

### Inverted/adjacent lookups

```python
def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
    source_ids = self.store.linker.connected(Identifier.get(id))
    refs: Set[str] = set()
    for source_id in source_ids:
        for dataset, version in self.vers:
            prefix = f"d:{dataset}:{version}:i:{source_id}:"
            for key, _ in self._prefix_scan(prefix):
                ref_entity_id = key.split(":")[-1]
                refs.add(self.store.linker.get_canonical(ref_entity_id))

    for ref_canonical in refs:
        entity = self.get_entity(ref_canonical)
        if entity is None:
            continue
        for prop, value in entity.itervalues():
            if value == id and prop.reverse is not None:
                yield prop.reverse, entity
```

### Timestamp preservation

#### Background: zavod's `TimeStampIndex`

In zavod (`zavod/runtime/timestamps.py`), the `TimeStampIndex` builds a temporary
LevelDB index of `{entity_id}:{stmt_id} → first_seen` from the **previous version's**
statements. During `context.emit()`, each new statement's `first_seen` is looked up
in this index — if found, the previous `first_seen` is preserved; otherwise it's set
to the current run time. This is how statement histories survive across re-crawls.

The KVStore can replace this entirely because the previous version's statements are
already in the store under `d:{dataset}:{prev_version}:s:{entity_id}:...` keys, with
`first_seen` in the value tuple.

#### Functional spec

**`KVView.get_timestamps(entity_id: str) -> Dict[str, str]`**

Returns a mapping of `{stmt_id: first_seen}` for all statements belonging to
`entity_id` (raw, not canonical) across all dataset+version pairs in the view's scope.

- Scans `d:{dataset}:{version}:s:{entity_id}:` for each (dataset, version) in scope
- Extracts `stmt_id` from key position [6] and `first_seen` from value tuple position [4]
- Skips statements where `first_seen` is None or empty
- Does **not** apply the linker — operates on raw entity IDs (the caller knows the
  source entity ID from the statement it's about to write)
- Returns a flat dict; if the same `stmt_id` appears in multiple dataset+version
  pairs, the last one wins (in practice, each stmt_id is unique per dataset+version)

**Usage pattern** (in zavod, replacing `TimeStampIndex`):

```python
# Get view pinned to previous version
prev_view = store.view(dataset, versions={dataset.name: prev_version})
stamps = prev_view.get_timestamps(entity.id)

# For each new statement:
stmt.first_seen = stamps.get(stmt.id, current_run_time)
stmt.last_seen = current_run_time
```

**`KVWriter` with `timestamps=True`**

As a convenience for callers that want automatic timestamp backfilling during write:

```python
class KVWriter:
    def __init__(self, ..., timestamps: bool = False):
        self.timestamps = timestamps
        self.prev_version = store.get_latest(dataset.name) if timestamps else None
        self._ts_cache: Dict[str, Dict[str, str]] = {}

    def _get_prev_timestamps(self, entity_id: str) -> Dict[str, str]:
        """Fetch first_seen timestamps from previous version for this entity."""
        if entity_id in self._ts_cache:
            return self._ts_cache[entity_id]
        if self.prev_version is None:
            return {}
        stamps: Dict[str, str] = {}
        prefix = f"d:{self.ds_ver_prev}:s:{entity_id}:".encode(E)
        for key, value in self._prefix_scan(prefix):
            parts = key.decode(E).split(":")
            stmt_id = parts[6]
            vals = orjson.loads(value)
            first_seen = vals[4]
            if first_seen:
                stamps[stmt_id] = first_seen
        self._ts_cache[entity_id] = stamps
        return stamps

    def add_statement(self, stmt: Statement) -> None:
        if self.timestamps and self.prev_version:
            stamps = self._get_prev_timestamps(stmt.entity_id)
            prev_first_seen = stamps.get(stmt.id)
            if prev_first_seen:
                stmt.first_seen = prev_first_seen
        # ... normal write path
```

The `_ts_cache` is per-entity and prevents repeated prefix scans when multiple
statements for the same entity are added sequentially (which is the normal pattern).

Since the full key includes all components (entity_id, ext, stmt_id, schema, prop),
an alternative is an exact `GET` per statement — but a single prefix scan per entity
is cheaper than N individual GETs when an entity has many statements.

### Statements iteration

```python
def statements(self, resolve: bool = False) -> Generator[Statement, None, None]:
    for dataset, version in self.vers:
        prefix = f"d:{dataset}:{version}:s:"
        for key, value in self._prefix_scan(prefix):
            stmt = _unpack_from_kv(key.split(":"), value)
            if stmt.external and not self.external:
                continue
            if resolve:
                stmt = self.store.linker.apply_statement(stmt)
            yield stmt
```

Sequential scan over sorted keys — much faster than `SSCAN` + `SMEMBERS` per entity.

## Redis/KVRocks Protocol Considerations

### Prefix scans via SCAN vs. sorted iteration

Redis `SCAN` with `MATCH` pattern is O(N) over all keys — it checks every key in the hash table. This is the 20x slowdown noted in the permastore doc.

KVRocks, however, stores keys in RocksDB and `SCAN` with a prefix match can use the sorted key layout for efficient prefix iteration. This is the critical performance difference.

**Implementation**: Use `scan_iter(match=f"{prefix}*")` for prefix scans. On KVRocks this will be efficient; on vanilla Redis it won't be (but vanilla Redis isn't the target for production).

For batched writes, use `pipeline()` as we do today. KVRocks pipelines map to RocksDB WriteBatches internally.

### Alternative: raw string keys with MGET

For point lookups of known keys (e.g., timestamp merging), use `GET`/`MGET` directly rather than scan. The composite key design means we can construct exact keys when we know all the components.

## Relationship to Existing Stores

`KVStore` is added **alongside** `RedisStore` and `VersionedRedisStore` — the old
code stays untouched. Zavod and other consumers continue using the old stores until
they migrate separately.

| Concept | `VersionedRedisStore` | `KVStore` (new) |
|---------|----------------------|-----------------|
| Statement storage | Redis sets (`SADD`) | Individual KV keys with composite key |
| Canonicalization | At write time (none — raw IDs stored, no linker on write) | Late-binding at read time via linker |
| Versioning | Yes (lists + set keys) | Yes (meta KV keys) |
| Entity membership | Redis set `ents:{ds}:{ver}` | Entity marker keys `d:{ds}:{ver}:e:{id}` |
| Full iteration | `SSCAN` + `SMEMBERS` per entity | Prefix scan over entity markers |
| `update()` | Noop | Noop (back-compat) |
| `pop()` | `NotImplementedError` | `NotImplementedError` |
| Release on close | Auto-releases | Explicit only |
| `get_latest`, `get_history`, `has_version`, `release_version`, `drop_version` | Yes | Yes (carried over) |
| `get_timestamps` | Yes | Yes |
| `statements(resolve=)` | Yes | Yes |

## What Stays the Same

- `Store`/`View`/`Writer` base classes — unchanged
- `RedisStore`, `VersionedRedisStore` — unchanged, kept for existing callers
- `LevelDBStore` — stays as the ephemeral/local store (migrating to rocksdict separately)
- `MemoryStore` — stays for tests and small workflows
- `SQLStore` — stays for its use cases
- `store.assemble()` — unchanged, still does entity-property canonicalization
- Wire format: orjson-packed tuples for values
- **Locking** — deferred. Readers may see partial state during version transitions. Acceptable for current usage patterns (typically 1 writer + 1 reader per dataset).

## Implementation Steps

All steps are within nomenklatura only. Zavod migration is out of scope.

### Step 1: `nomenklatura/store/kv.py` — core implementation

New file with `KVStore`, `KVWriter`, `KVView`. Uses `redis.client.Redis` as the
backend (works with both Redis and KVRocks). Reuses the existing `get_redis()` /
`close_redis()` from `nomenklatura.kv` for connection management, but does not use
the `b()` helper — all `.encode(E)` calls are inline for performance.

~300-400 lines, modeled on `level.py`'s performance-sensitive style (unrolled loops,
minimal helper calls).

### Step 2: Export from `nomenklatura/store/__init__.py`

Add `KVStore` to the store package exports so it's available as
`from nomenklatura.store import KVStore`. No other wiring changes within nomenklatura
— the old stores remain importable and functional.

### Step 3: Tests

- Add new test file `tests/test_store_kv.py`
- Test write → release → read cycle
- Test late-binding behavior: write under source IDs, read resolves to canonical
- Test version lifecycle: write, release, read, drop, latest pointer update
- Test `get_timestamps`, `statements(resolve=True/False)`, `get_inverted`, `entities`
- Test schema pre-filtering in `entities(include_schemata=...)`
- Test external statement filtering
- Use `fakeredis` as the backend (same as existing store tests)

## Open Questions

1. **`fakeredis` and prefix scans** — `fakeredis` implements `SCAN` with `MATCH` but doesn't have KVRocks's sorted-key optimization. Tests will work correctly but won't reflect production performance characteristics. Acceptable for correctness testing; benchmarking needs KVRocks.

2. **Schema in entity marker vs. first-statement schema** — The entity marker stores the schema from the last `add_statement` call for that entity. With late binding, a merged entity may span multiple schemas. The marker schema is a hint for pre-filtering, not authoritative — `assemble()` computes the real schema. Should the marker store all observed schemas? Probably not worth the complexity; a false positive (marker says Person, assembly says LegalEntity) just means we assemble and then skip — same as the current LevelDB behavior.

3. **Key encoding: string vs. bytes** — The current design uses string keys with `:` separators (matching bahamut). Redis treats keys as bytes, so we `.encode()` everywhere. Could use a binary encoding for tighter keys, but readability and debuggability of string keys is valuable. String keys it is.

4. **Batch size tuning** — The `VersionedRedisStore` uses 2,000 statement batches; `RedisStore` uses 100,000. The KV approach should tolerate larger batches since each statement is an independent `SET` rather than an `SADD` to a shared set. Start with 50,000 and tune.

5. **`pop()` semantics** — The base `Writer` defines `pop()` for merge operations. With late binding this is unnecessary for the KV store, but the `LevelDBStore` (which does write-time canonicalization) still needs it. We can raise `NotImplementedError` in `KVWriter.pop()` (same as `VersionedRedisWriter` today).
