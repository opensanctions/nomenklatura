---
description: Plan to migrate nomenklatura's LevelDB store (plyvel) to RocksDB via rocksdict
date: 2026-03-14
tags: [nomenklatura, rocksdb, leveldb, plyvel, rocksdict, store]
---

# Migrate LevelDB Store to RocksDB (rocksdict)

## Context

The store is **ephemeral** -- it gets built as part of the xref and export
processes, used to generate an export, and then discarded. There is no long-lived
database. This means:

- **Data migration is irrelevant.** No existing LevelDB databases need to be
  preserved or opened by RocksDB. Each run creates a fresh store.
- **Write-heavy, then read-heavy, then delete.** The lifecycle is: bulk ingest
  all statements -> iterate/query to produce exports -> discard the directory.
- **Startup and bulk-load speed matter.** The faster we can ingest statements
  into the store, the faster the overall pipeline runs.
- **Durability/WAL is unnecessary overhead.** We don't need crash recovery since
  the store can always be rebuilt from source data.

## Why migrate

- `plyvel` wraps LevelDB, which is unmaintained (last Google release: 2017)
- RocksDB is a maintained successor with better compaction, compression, and
  performance characteristics
- `rocksdict` provides pre-built wheels for Linux/macOS/Windows, Python 3.7-3.14
- For this ephemeral workload, RocksDB can be tuned for significantly faster
  bulk ingest (disable WAL, increase write buffer, defer compaction)

## Feasibility Assessment

The LevelDB store in `nomenklatura/store/level.py` uses a small subset of the
plyvel API:

| plyvel feature used | rocksdict equivalent | Migration difficulty |
|---------------------|---------------------|---------------------|
| `DB(path, create_if_missing=True, ...)` | `Rdict(path, options=opts)` | Trivial -- different options API |
| `db.close()` | `db.close()` | Identical |
| `db.put(key, value)` | `db[key] = value` | Trivial |
| `db.delete(key)` | `del db[key]` | Trivial |
| `db.write_batch()` | `WriteBatch(raw_mode=True)` + `db.write(wb)` | Minor rework |
| `batch.put(k, v)` / `batch.delete(k)` | Same API | Identical |
| `batch.write()` | `db.write(batch)` | Inverted call |
| `db.iterator(prefix=b"...")` | Manual: `db.items(from_key=prefix, read_opt=ro)` with upper bound | **Main work** |
| `db.iterator(prefix=..., include_value=False)` | `db.keys(from_key=prefix, read_opt=ro)` with upper bound | Same pattern |
| `db.iterator(prefix=..., fill_cache=False)` | `ReadOptions().fill_cache(False)` | Trivial |
| `db.compact_range()` | `db.compact_range()` | Identical |
| `max_open_files`, `write_buffer_size`, `lru_cache_size` | `Options()` setters | Different API, same concepts |

**Verdict: Straightforward migration.** No custom merge operators, comparators,
or filters are needed. The only non-trivial part is replacing plyvel's built-in
`prefix=` iterator parameter.

## Key Design Decisions

### Prefix iteration strategy

The store uses prefix iteration extensively with patterns like:
- `s:{canonical_id}:` -- get all statements for an entity
- `i:{id}:` -- get inverted index entries
- `s:` -- iterate all statements

Since prefixes are variable-length (entity IDs vary), the best approach is
**iterate_upper_bound**:

```python
from rocksdict import ReadOptions

def _prefix_read_opts(prefix: bytes, fill_cache: bool = True) -> ReadOptions:
    ro = ReadOptions(raw_mode=True)
    ro.set_iterate_upper_bound(_next_prefix(prefix))
    if not fill_cache:
        ro.fill_cache(False)
    return ro

def _next_prefix(prefix: bytes) -> bytes:
    """Compute the lexicographic successor of a prefix for upper-bound iteration."""
    # Increment the last byte; handle overflow by trimming
    ba = bytearray(prefix)
    for i in range(len(ba) - 1, -1, -1):
        if ba[i] < 0xFF:
            ba[i] += 1
            return bytes(ba[: i + 1])
    # All 0xFF -- no upper bound needed (won't happen with our key scheme)
    return b"\xff"
```

This is a ~10 line utility that replaces all `iterator(prefix=...)` calls.

### raw_mode

rocksdict defaults to "pickle mode" which serializes Python objects. We need
`raw_mode=True` everywhere since the store manages its own serialization via
`orjson`. This must be set on `Rdict`, `WriteBatch`, and `ReadOptions`.

### Ephemeral store tuning

Since the store is built, used, and discarded, we can disable durability features
and tune aggressively for bulk ingest + sequential read:

```python
opts = Options(raw_mode=True)
opts.create_if_missing(True)

# Disable WAL -- no crash recovery needed for ephemeral stores
# WriteBatch still needs: WriteOptions with disable_wal=True
# (rocksdict exposes this via Rdict write options)

# Larger write buffer = fewer flushes during bulk ingest
opts.set_write_buffer_size(64 * 1024 * 1024)  # 64MB (vs current 20MB default)
opts.set_max_write_buffer_number(3)

# Defer compaction during ingest, compact once before reads
opts.set_disable_auto_compactions(True)
# After ingest: db.compact_range() once, then read

# Compression: zstd gives ~30% better ratio than snappy at similar speed
# RocksDB defaults to this already

# Parallelism for compaction/flush
opts.increase_parallelism(os.cpu_count() or 4)
```

The pattern becomes:
1. Open with auto-compaction disabled
2. Bulk-write all statements in large batches
3. Call `compact_range()` once (already done in `optimize()`)
4. Read/iterate for export
5. Close and delete directory

This should be meaningfully faster than the current LevelDB setup for the
bulk-ingest phase, since LevelDB cannot disable WAL or defer compaction.

## Implementation Plan

### Step 1: Add rocksdict dependency

In `nomenklatura`'s `pyproject.toml`, replace `plyvel` with `rocksdict >= 0.3.20`.

### Step 2: Create `nomenklatura/store/rocks.py`

New file implementing `RocksDBStore`, `RocksDBWriter`, `RocksDBView` following
the same patterns as `level.py` but using rocksdict. Key changes:

```python
from rocksdict import Options, Rdict, ReadOptions, WriteBatch

class RocksDBStore(Store[DS, SE]):
    def __init__(self, dataset: DS, linker: Linker[SE], path: Path):
        super().__init__(dataset, linker)
        self.path = path
        opts = Options(raw_mode=True)
        opts.create_if_missing(True)
        opts.set_max_open_files(settings.ROCKSDB_MAX_FILES)
        opts.set_write_buffer_size(settings.ROCKSDB_BUFFER * 1024 * 1024)
        opts.set_max_write_buffer_number(3)
        opts.set_disable_auto_compactions(True)  # compact once before reads
        opts.increase_parallelism(os.cpu_count() or 4)
        self.db = Rdict(path.as_posix(), options=opts)
```

**Writer changes:**
- `self.batch = WriteBatch(raw_mode=True)` instead of `self.store.db.write_batch()`
- `self.store.db.write(self.batch)` instead of `self.batch.write()`

**View iteration changes:**
- Replace `db.iterator(prefix=prefix)` with
  `db.items(from_key=prefix, read_opt=_prefix_read_opts(prefix))`
- Replace `db.iterator(prefix=prefix, include_value=False)` with
  `db.keys(from_key=prefix, read_opt=_prefix_read_opts(prefix))`
- Replace `db.iterator(prefix=b"s:", fill_cache=False)` with
  `db.items(from_key=b"s:", read_opt=_prefix_read_opts(b"s:", fill_cache=False))`
- No context manager needed -- rocksdict iterators are plain Python iterators

**Note on `with ... as it` pattern:** plyvel iterators are context managers that
must be closed. rocksdict iterators are regular Python generators. The `with`
blocks in level.py become plain `for` loops.

### Step 3: Update settings

Rename `LEVELDB_*` settings to `ROCKSDB_*`:
- `NOMENKLATURA_ROCKSDB_MAX_FILES` (default: 500)
- `NOMENKLATURA_ROCKSDB_BUFFER` (default: 64, in MB -- increased from 20)

### Step 4: Update imports / store registration

Update `nomenklatura/store/__init__.py` to export `RocksDBStore` instead of (or
alongside) `LevelDBStore`. Update any code that imports `LevelDBStore` directly.

### Step 5: Delete level.py

Once rocks.py is tested, remove `level.py` and the `plyvel` dependency.

### Step 6: Update tests

Update test fixtures that create `LevelDBStore` instances to use `RocksDBStore`.

## Line-by-line migration reference

For each plyvel usage in `level.py`:

| Line | plyvel call | rocksdict replacement |
|------|------------|----------------------|
| 65-71 | `plyvel.DB(path, create_if_missing=True, max_open_files=..., write_buffer_size=..., lru_cache_size=...)` | `Rdict(path, options=opts)` with `Options` configured |
| 75 | `self.db.compact_range()` | `self.db.compact_range()` |
| 94 | `self.db.close()` | `self.db.close()` |
| 117 | `self.store.db.write_batch()` | `WriteBatch(raw_mode=True)` |
| 107 | `self.batch.write()` | `self.store.db.write(self.batch)` |
| 134 | `self.batch.put(key, data)` | `self.batch.put(key, data)` |
| 138 | `self.batch.put(key, b"")` | `self.batch.put(key, b"")` |
| 150 | `self.store.db.iterator(prefix=prefix)` | `self.store.db.items(from_key=prefix, read_opt=ro)` |
| 152 | `self.batch.delete(k)` | `self.batch.delete(k)` |
| 159 | `self.batch.delete(...)` | `self.batch.delete(...)` |
| 173 | `self.store.db.iterator(prefix=prefix, include_value=False)` | `self.store.db.keys(from_key=prefix, read_opt=ro)` |
| 186 | `self.store.db.iterator(prefix=prefix)` | `self.store.db.items(from_key=prefix, read_opt=ro)` |
| 199 | `self.store.db.iterator(prefix=prefix, include_value=False)` | `self.store.db.keys(from_key=prefix, read_opt=ro)` |
| 212 | `self.store.db.iterator(prefix=b"s:", fill_cache=False)` | `self.store.db.items(from_key=b"s:", read_opt=ro_no_cache)` |

## Risks

1. **Wheel availability** -- rocksdict has wheels for all major platforms. If a
   platform is missing, users would need to compile rust-rocksdb from source
   (requires Rust toolchain). Unlikely for Linux/macOS.

2. **rocksdict API stability** -- rocksdict is at 0.3.x. Pin to a minimum version
   and test in CI.

3. **Disk usage during ingest** -- With WAL disabled and compaction deferred, the
   on-disk size may spike during bulk ingest before the final `compact_range()`
   call. Monitor this but it should be fine since the store is ephemeral.

## Effort Estimate

This is a **small-to-medium** task. The store implementation is ~220 lines, and the
migration is mechanical -- the key/value schema and serialisation format stay
identical. Estimated: 1-2 sessions to implement, test, and clean up.
