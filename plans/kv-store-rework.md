---
description: Rework KVStore read path to eliminate per-entity SCAN round-trips
date: 2026-03-15
tags: [permastore, kv, performance, redis, kvrocks]
---

# KVStore read path rework

## Problem

The KV store write path is acceptable (~25K statements/s to KVRocks), but the read
path is unusable. `view.entities()` can't deliver 10K entities in reasonable time
against the sanctions collection (~4.7M statements, ~500K entities).

### Why it's slow

LevelDB `entities()` does **one sequential iterator** over all `s:` keys. Statements
are sorted by canonical ID, so entity boundaries are detected by key change. One pass,
zero round-trips, ~200K+ stmts/s.

KV `entities()` does:

1. `scan_iter(d:{ds}:{ver}:e:*)` for each dataset×version → many SCAN commands
2. Per entity marker found, calls `get_entity(canonical_id)` which does:
   - `linker.connected_plain(id)` → list of source IDs in the canonical cluster
   - For each source ID × each dataset×version: `scan_iter(d:{ds}:{ver}:s:{sid}:*)`
     + `mget` batch
3. Result: **O(entities × source_ids × dataset_versions)** SCAN round-trips

With ~100 dataset versions in scope and ~500K entities, that's millions of SCAN
commands. Each SCAN is a server round-trip, even over localhost.

### Why point lookups are also slow

`get_entity(id)` suffers the same problem: `connected_plain(id)` × dataset×versions
= many SCANs per lookup. For merged entities with multiple referents, this multiplies
further.

## Design constraints

- Must keep **late-binding canonicalization** (statements stored under source entity
  IDs, linker resolves at read time).
- Must keep **dataset versioning** (multiple versions can coexist; readers lock to
  specific versions).
- Must use **Redis protocol** (KVRocks; no custom server).
- Entity assembly stays in Python (no FtM logic duplication).

## Approach: batch-oriented read path

The fundamental insight: **don't do per-entity round-trips during iteration.** Instead,
stream all relevant data in bulk passes and assemble in Python.

### Phase 1: Bulk entity scan with pipelining

Replace the per-entity `get_entity()` call in `entities()` with a bulk streaming
approach:

```
1. Collect ALL entity markers in one pass (scan_iter over e: prefixes)
2. Build canonical grouping in memory (source_id → canonical_id via linker)
3. Stream ALL statements in one pass (scan_iter over s: prefixes)
4. Assemble entities from the statement stream
```

This reduces round-trips from O(entities × versions) to O(versions) — one SCAN
pass per dataset×version for markers, one for statements.

#### Implementation sketch for `entities()`

```python
def entities(self, include_schemata=None):
    # Step 1: Stream all statements across all dataset×versions in bulk.
    # Group by canonical_id in memory as they arrive.
    # Yield assembled entities.

    canonical_stmts: dict[str, list[Statement]] = {}
    seen_canonicals: list[str] = []  # preserve discovery order

    for ds, ver in self.vers:
        prefix = f"d:{ds}:{ver}:s:".encode(E)
        for key, value in self._prefix_scan(prefix):
            parts = key.decode(E).split(":")
            entity_id = parts[4]
            ext = parts[5]
            if ext == "x" and not self.external:
                continue

            canonical_id = self.store.linker.get_canonical(entity_id)
            stmt = _unpack_statement(parts, value, canonical_id)

            if canonical_id not in canonical_stmts:
                canonical_stmts[canonical_id] = []
                seen_canonicals.append(canonical_id)
            canonical_stmts[canonical_id].append(stmt)

    # Assemble and yield
    for canonical_id in seen_canonicals:
        stmts = canonical_stmts.pop(canonical_id)
        entity = self.store.assemble(stmts)
        if entity is not None:
            if include_schemata is not None:
                if entity.schema not in include_schemata:
                    continue
            yield entity
```

**Trade-off**: This buffers all statements in memory. For the sanctions collection
(~4.7M stmts), that's ~2–4 GB. Acceptable for a production server with 8+ GB RAM.
For enrichment (150M stmts), this won't work — but that's a separate scale problem.

#### Memory-bounded variant

Process one dataset×version at a time, yielding entities that are complete (all
their source IDs have been seen). Requires tracking which canonicals span multiple
datasets — the minority case (most entities come from one source dataset).

```python
def entities(self, include_schemata=None):
    pending: dict[str, list[Statement]] = {}
    yielded: set[str] = set()

    for ds, ver in self.vers:
        prefix = f"d:{ds}:{ver}:s:".encode(E)
        for key, value in self._prefix_scan(prefix):
            # ... parse, canonicalize, accumulate into pending ...

    # After all passes, yield everything
    for canonical_id, stmts in pending.items():
        if canonical_id in yielded:
            continue
        yielded.add(canonical_id)
        entity = self.store.assemble(stmts)
        if entity is not None:
            yield entity
```

Actually, since we must scan all dataset×versions anyway (an entity may have
statements from multiple datasets), full buffering is unavoidable unless we
do two passes: one for discovery, one for fetch.

### Phase 2: Faster `_prefix_scan` via SCAN cursor + pipeline

The current `_prefix_scan` does `scan_iter` to collect keys, then `mget` in
batches. This is two round-trips per batch: one for SCAN, one for MGET.

KVRocks supports `SCAN` with `MATCH` and `COUNT`, but each SCAN cursor step
is a round-trip. For a prefix with 100K keys, that's 100+ round-trips even
with COUNT=1000.

**Alternative: use sorted set or hash per entity?** No — this changes the data
model and loses the prefix-scan alignment that makes LevelDB fast.

**Alternative: Lua scripting on KVRocks.** KVRocks supports `EVAL`. A server-side
Lua script could SCAN + collect values in one round-trip:

```lua
local cursor = "0"
local result = {}
repeat
    local scan_result = redis.call("SCAN", cursor, "MATCH", KEYS[1], "COUNT", 1000)
    cursor = scan_result[1]
    local keys = scan_result[2]
    if #keys > 0 then
        local vals = redis.call("MGET", unpack(keys))
        for i, k in ipairs(keys) do
            table.insert(result, k)
            table.insert(result, vals[i])
        end
    end
until cursor == "0"
return result
```

This reduces per-prefix round-trips from O(keys/1000) to **1**. Significant for
point lookups where an entity has 10–50 statements.

**Risk**: Lua scripts block the KVRocks event loop. A scan over a large prefix
(e.g., a dataset with 1M statements) would block all other clients. Acceptable
for single-client benchmarks, problematic for production concurrency.

### Phase 3: Faster point lookups via `get_entity()`

For single-entity lookups (the export adjacency path), the current code does:

```
connected_plain(id) → [sid1, sid2, ...]
for each sid:
    for each (ds, ver):
        scan_iter(d:{ds}:{ver}:s:{sid}:*) + mget
```

**Improvement 1**: Pipeline all SCAN commands across source IDs and versions:

```python
def get_entity(self, id: str) -> Optional[SE]:
    canonical_id = self.store.linker.get_canonical(id)
    source_ids = list(self.store.linker.connected_plain(id))
    statements: list[Statement] = []

    # Collect all keys first via pipelined SCANs
    all_keys: list[bytes] = []
    for sid in source_ids:
        for ds, ver in self.vers:
            prefix = f"d:{ds}:{ver}:s:{sid}:"
            for key in self.store.db.scan_iter(match=prefix.encode(E) + b"*"):
                all_keys.append(key)

    # Single MGET for all values
    if all_keys:
        values = self.store.db.mget(all_keys)
        for key, value in zip(all_keys, values):
            if value is None:
                continue
            parts = key.decode(E).split(":")
            if parts[5] == "x" and not self.external:
                continue
            statements.append(_unpack_statement(parts, value, canonical_id))

    return self.store.assemble(statements)
```

**Improvement 2**: If entities are overwhelmingly singletons (source_id = canonical_id,
one dataset), optimize the fast path:

```python
def get_entity(self, id: str) -> Optional[SE]:
    canonical_id = self.store.linker.get_canonical(id)
    source_ids = list(self.store.linker.connected_plain(id))

    # Fast path: singleton, unmerged
    if len(source_ids) == 1 and len(self.vers) == 1:
        ds, ver = self.vers[0]
        return self._get_single_entity(source_ids[0], ds, ver, canonical_id)

    # ... general path ...
```

**Improvement 3**: Lua script per entity (see Phase 2). One round-trip per entity
regardless of statement count.

### Phase 4: Consider alternative data model (Hash per entity)

Instead of flat keys, store each entity's statements as a Redis Hash:

```
Key:   d:{dataset}:{version}:s:{entity_id}
Field: {ext}:{stmt_id}:{schema}:{property}
Value: packed statement data
```

Then `HGETALL d:{ds}:{ver}:s:{entity_id}` retrieves all statements for an entity
in **one command, one round-trip**. For `entities()`, iterate entity markers and
`HGETALL` each one.

**Pros:**
- Point lookup: 1 round-trip per source_id × version (vs. many SCANs)
- Bulk iteration: pipeline `HGETALL` for batches of entities
- Redis Hash is the natural fit for "get all fields of an object"

**Cons:**
- Loses prefix-scan ordering within an entity (irrelevant — we assemble all stmts)
- KVRocks Hash implementation may have different performance characteristics
- Inverted index stays as flat keys (it's already fine — small values, few lookups)
- Entity marker becomes redundant (just check if the hash key exists: `EXISTS`)

**Implementation:**

Writer:
```python
def add_statement(self, stmt):
    hash_key = f"d:{self.ds_ver}:s:{stmt.entity_id}".encode(E)
    field = f"{ext}:{stmt.id}:{stmt.schema}:{stmt.prop}".encode(E)
    value = orjson.dumps((stmt.value, stmt.lang or 0, ...))
    self._pipeline.hset(hash_key, field, value)
    # Inverted index unchanged
    # Entity marker: just the hash existence, but keep e: for schema pre-filter
```

View.get_entity:
```python
def get_entity(self, id):
    canonical_id = self.store.linker.get_canonical(id)
    statements = []
    pipe = self.store.db.pipeline()
    keys = []
    for sid in self.store.linker.connected_plain(id):
        for ds, ver in self.vers:
            k = f"d:{ds}:{ver}:s:{sid}".encode(E)
            pipe.hgetall(k)
            keys.append((ds, ver, sid))
    results = pipe.execute()
    for (ds, ver, sid), fields in zip(keys, results):
        if not fields:
            continue
        for field, value in fields.items():
            parts = field.decode(E).split(":")
            # ... unpack and append ...
    return self.store.assemble(statements)
```

View.entities:
```python
def entities(self, include_schemata=None):
    # Collect all entity hash keys
    entity_keys: dict[str, list[tuple[str, str, str]]] = {}  # canonical → [(ds, ver, sid)]
    for ds, ver in self.vers:
        marker_prefix = f"d:{ds}:{ver}:e:".encode(E)
        for key, schema_bytes in self._prefix_scan(marker_prefix):
            entity_id = key.decode(E).split(":")[4]
            canonical_id = self.store.linker.get_canonical(entity_id)
            if canonical_id not in entity_keys:
                entity_keys[canonical_id] = []
            entity_keys[canonical_id].append((ds, ver, entity_id))

    # Batch HGETALL in pipeline chunks
    BATCH = 200
    canonical_ids = list(entity_keys.keys())
    for i in range(0, len(canonical_ids), BATCH):
        batch_ids = canonical_ids[i:i+BATCH]
        pipe = self.store.db.pipeline()
        batch_lookups = []
        for cid in batch_ids:
            for ds, ver, sid in entity_keys[cid]:
                pipe.hgetall(f"d:{ds}:{ver}:s:{sid}".encode(E))
                batch_lookups.append((cid, ds, ver, sid))
        results = pipe.execute()

        # Group results by canonical
        by_canonical: dict[str, list[Statement]] = {}
        for (cid, ds, ver, sid), fields in zip(batch_lookups, results):
            if not fields:
                continue
            canonical_id = cid
            for field, value in fields.items():
                # ... unpack statement ...
                pass
            # accumulate into by_canonical[cid]

        for cid in batch_ids:
            stmts = by_canonical.get(cid, [])
            if not stmts:
                continue
            entity = self.store.assemble(stmts)
            if entity is not None:
                yield entity
```

This approach trades the O(entities × versions) SCAN problem for O(entities / batch)
pipelined HGETALL commands. With batch=200, a 500K entity collection needs 2,500
pipeline round-trips — orders of magnitude better.

## Recommendation

**Phase 4 (Hash per entity)** is the right approach. It aligns with Redis's data model
instead of fighting it:

- Redis is designed for key→value or key→hash lookups, not ordered range scans
- HGETALL is O(fields) with one round-trip — exactly what entity assembly needs
- Pipelined HGETALL for bulk iteration is the natural Redis batch pattern
- The entity marker (`e:` keys) can stay for schema pre-filtering during discovery
- The inverted index (`i:` keys) stays as-is — it's small and rarely scanned in bulk

**Expected performance improvement:**
- Point lookup: from O(source_ids × versions × scan_rounds) to O(source_ids × versions)
  pipelined HGETALLs ≈ 1–2 round-trips for typical entities
- Bulk iteration: from millions of SCANs to ~2,500 pipelined batches for 500K entities
- Write throughput: similar — HSET vs SET is comparable

## Implementation plan

1. Modify `KVWriter.add_statement()` to use HSET instead of SET for statement data
2. Modify `_unpack_statement` to work with hash field+value instead of full key+value
3. Rewrite `KVView.get_entity()` to use pipelined HGETALL
4. Rewrite `KVView.entities()` to use batched marker scan + pipelined HGETALL
5. Update `KVView.has_entity()` to use EXISTS on hash key
6. Update `KVView.get_timestamps()` for the new key layout
7. Update `KVStore.drop_version()` for hash keys
8. Benchmark against current implementation
