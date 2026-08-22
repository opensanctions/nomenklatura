---
description: Spec for the materialized DuckDB batch store (duckdb_batch.py) — per-view materialization sorted on canonical_id, SQL update() keyed on source entity ids, a typed input-relation contract owned by the store, no persistent mapping or entity-props tables. Lazy live store deferred to web-dedupe.
date: 2026-08-22
tags: [nomenklatura, store, duckdb, xref, dedupe, resolver, memory]
---

# DuckDB batch store

## Scope decision

Two use cases exist for a DuckDB statement store, with opposite invariants about
where resolution lives:

- **Batch** (zavod export/enrich, xref, dedupe TUI): heavy read loop over a fixed
  scope; build cost of seconds is irrelevant; resolution is baked into the data
  at build and mutated in place via `update()`.
- **Live** (future web-based dedupe loop): store outlives resolver changes;
  no materialization; every query lazy-resolves through the live linker
  (`entity_id IN (…referents…)`), so decisions are visible instantly and the
  data artifact never goes stale. Zero-DDL, works on read-only connections.

**We build only the batch store now**, as `nomenklatura/store/duckdb_batch.py`
(replacing the draft `duckdb_.py`). The live store is a separate future
implementation, revisited when web-dedupe starts (months out). The draft's middle
mode — querying through a canonical join without materializing — serves neither
case and is dropped.

## Discovery: how views are actually used

Surveyed all non-test store/view usage in zavod and nomenklatura:

| Flow | views per store | external | calls `update()` |
|---|---|---|---|
| `zavod etl export` / `run` | 1 | False | no |
| `zavod enrich` (remote) | 1 | True | no |
| local enricher | 1 each on **two separate stores** (subject + target) | gated / False | no |
| xref (`nomenklatura/xref.py`) | 1 | True | yes — auto-merge, hot (thousands/run) |
| dedupe TUI (`tui/dedupe.py`) | 1, held for whole session | True | yes — per decision |
| `zavod dedupe-edges` | 1 | True | no |

Findings:

- **1 store : 1 view in every production flow.** Multiple views per store occur
  only in tests. Views are long-lived (session/run lifetime) and never created in
  a loop.
- **`get_inverted()` consumers are all batch**: zavod exporters (fragment,
  securities, senzing, simplecsv), validators, local enricher, wikidata
  reconcile. The edges table stays.
- **`update()` semantics** (base class): re-key all statements of the cluster's
  referents to the new canonical id. Splits after a NEGATIVE arrive as two
  `update()` calls, one per surviving cluster — the same shape works as SQL
  UPDATEs keyed on source entity ids.

## Design

### Materialize per view, at view creation

Decision: **materialize when the view is created**, one set of tables per view.
The usage survey makes this safe (one view per store in practice) and it buys
real simplification:

- At `view(scope, external)` time the actual leaf-dataset set and the external
  flag are known. Bake them into the materialization `WHERE` clause.
- Consequence: **all per-query filters disappear.** The current `_filters()`
  (dataset `IN` list + `NOT external` on every query) is redundant against a
  table that only contains the view's scope. Queries become pure probes/scans.
- Excluding externals at build (the export path) skips what can be the bulk of
  an enriched relation — smaller build, smaller scans.
- Tables are named per view (e.g. `nk_stmts_1`, `nk_edges_1` with a store-level
  counter) so a second view doesn't clobber the first. Two views on one store
  duplicate storage; that's tests-only today and acceptable — document it.
- The store keeps a list of the views it created, for `update()` fan-out. Views
  are never closed/discarded in practice, so the registry pinning them is fine.

### Build sequence (per view)

1. **Mapping table**: `CREATE TABLE nk_mapping_<n> (entity_id, canonical_id)`,
   filled from **`Linker.mappings()`** (the new method — every known identifier
   incl. canonical self-rows) in batched inserts. Built fresh from the live
   linker at each view creation, so a second view sees decisions made since the
   first.
2. **Statement table**: join relation × mapping with
   `coalesce(c.canonical_id, s.entity_id)`, filtered to the view's datasets
   (and `NOT external` if external=False), written **`ORDER BY canonical_id`**
   (clustered row groups, zone-map pruning), then an ART index on
   `canonical_id`.
3. **Edges table**: one scan of the statement table for entity-typed props,
   with the (schema, prop) pairs inlined as a `VALUES` list in the build query —
   **no persistent `nk_entity_props` table**. Value-side canonicals via a join
   against the mapping table.
4. **Drop the mapping table.** It is a build-time artifact only. After the
   build, all canonicalisation goes through the linker in Python; nothing keeps
   it current, nothing reads it.

### Reads

As in the current draft, minus the filter clauses:

- `get_entities(ids)`: canonicalize ids via linker, single
  `canonical_id IN (…)` probe, group rows by canonical, assemble.
- `entities()`: full scan `ORDER BY canonical_id`, streaming group-by.
- `get_inverted(id)`: probe edges on `value_canonical_id`, then batch-fetch
  owners.
- Per-query cursors (`conn.cursor()`) so concurrent iteration works — this is
  why the tables are regular, not TEMP (temp tables are invisible to cursor
  duplicates).

### update()

Keyed on **original entity ids** from the live linker, fanned out to every
registered view's tables:

```sql
UPDATE nk_stmts_<n> SET canonical_id = ? WHERE entity_id IN (…referents)
UPDATE nk_edges_<n> SET origin_canonical_id = ? WHERE origin_entity_id IN (…)
UPDATE nk_edges_<n> SET value_canonical_id = ? WHERE value_entity_id IN (…)
```

- A statement re-keyed to a new canonical is fetched by later reads because
  reads probe by value, not by position; the physical sort degrades gradually
  (DuckDB updates are delete+insert) — acceptable within a run.
- The xref auto-merge cadence is the hot case. Without an `entity_id` index each
  UPDATE scans; with one, builds and updates pay ART maintenance. **Measure
  before choosing** (open question 2). Note: statements arriving in a cluster
  via `update()` land outside the canonical sort order but stay indexed — reads
  are unaffected in correctness.
- Rows whose `entity_id` is not in the table (referents from other datasets) are
  simply not matched — no-op, correct.
- After `update()`, the external flag semantics are unchanged: re-keying never
  moves a statement across the view's external/scope boundary, since those are
  statement-level attributes.

### Interface

- Constructor: `DuckDBBatchStore(dataset, linker, conn, relation)` — caller owns
  the connection and the relation (parquet view, table, whatever). Validate the
  relation name and check the relation against the input contract (below) at
  init, fail loudly.
- `writer()` raises — the store consumes artifacts produced elsewhere;
  `update()` is the only mutation.
- `close()` **drops this store's `nk_*` tables** and leaves the caller's
  connection open. Reusing a materialization across processes is a different
  feature; the tables are run-scoped state, not artifacts.

## Input relation contract

The store defines expectations about the relation it is handed; that contract
should be explicit and validated, not implicit in the `SELECT` list. Producer
flow (zavod): the crawl writes the statements CSV/pack → an import step types
it and pre-processes it (dedupe on `id`, coalesce `first_seen` from previous
runs, etc.) → the resulting table/parquet is handed to the store. See
opensanctions PR #5243 (`contrib/zavodlake/convert.py`), whose conversion
already produces exactly this shape.

**The contract lives in a new `nomenklatura/duck.py` module**, not in the store
module: producers (the zavod import/pre-processing step) target the contract
without being intrinsically linked to the store, and the store validates
against the same spec at init. `duck.py` is the DuckDB counterpart to
`nomenklatura/db.py` (which plays exactly this role for SQLAlchemy with
`make_statement_table` and engine management). If the contract ever needs to be
shared against the dependency direction (e.g. yente), it can move to
followthemoney next to `CSV_COLUMNS` — not now.

### The `duck.py` module

Three responsibilities, all in scope for this change:

1. **Statement relation contract**: the column→type spec (table below).
2. **Validation helper**: check a relation's names and types against the spec
   via `DESCRIBE`; the store calls it at init, producers can call it after
   import.
3. **Connection management**: a factory/config builder generalizing what
   `blocker/index.py` builds inline today —
   `preserve_insertion_order = false` (large CTAS/COPY memory; safe here since
   anything order-sensitive carries an explicit `ORDER BY`),
   `python_enable_replacements = false`, `memory_limit` from a per-call
   override falling back to `NOMENKLATURA_DUCKDB_MEMORY` (MB), `threads` from
   `NOMENKLATURA_DUCKDB_THREADS`. Memory/thread management is needed by the
   batch store's materialization joins just as much as by the blocker.
   The blocker migrates onto the shared helper in this change (small, contained
   refactor of its `__init__`).

Connection ownership is unchanged: the producer (or other caller) creates the
connection — normally through the `duck.py` factory — builds/attaches the
relation, and hands the same connection to the store.

The columns, aligned with the zavodlake conversion:

| column | DuckDB type | notes |
|---|---|---|
| `id` | VARCHAR NOT NULL | unique; producer dedupes on it |
| `entity_id` | VARCHAR NOT NULL | |
| `schema` | VARCHAR NOT NULL | already split out of the packed `Schema:prop` |
| `prop` | VARCHAR NOT NULL | |
| `value` | VARCHAR NOT NULL | |
| `dataset` | VARCHAR NOT NULL | leaf dataset name |
| `lang` | VARCHAR | nullable |
| `original_value` | VARCHAR | nullable |
| `origin` | VARCHAR | nullable |
| `external` | BOOLEAN NOT NULL | |
| `first_seen` | TIMESTAMP | naive UTC; nullable |
| `last_seen` | TIMESTAMP | naive UTC; nullable |

Deliberate differences from `nomenklatura.db.make_statement_table` (the mutable
SQLStore table): **no `canonical_id`** (resolution is the store's job, never the
artifact's — this is the whole design) and **no `prop_type`** (derivable from
schema metadata; the SQL column exists for query-side filtering the DuckDB
store doesn't do).

Semantics worth writing into the spec:

- `TIMESTAMP` (not VARCHAR) for the seen-columns is what makes the
  previous-timestamps pre-processing a SQL `least()`/`coalesce()` on the
  producer side; the store converts back to the Statement string form
  (`strftime('%Y-%m-%dT%H:%M:%S')`) on read.
- Sorting by `entity_id` and zstd parquet are **recommendations, not
  requirements** for the batch store (the build is one full-scan join either
  way); entity_id-clustering becomes load-bearing only for the future live
  store.
- Validation at store init: names *and* types via `DESCRIBE`, not just a
  `SELECT … LIMIT 0` probe — a mistyped `external` or VARCHAR timestamp should
  fail at construction, not produce garbage mid-run.
- **No VARCHAR max lengths** (decided): DuckDB parses but discards
  `VARCHAR(n)` — no enforcement, and `DESCRIBE` strips it, so validation
  couldn't check it. Value bounds are owned upstream by followthemoney
  (`PROP_VALUE_MAX` etc.); `db.py`'s `KEY_LEN`/`VALUE_LEN` serve
  Postgres/MySQL index constraints that don't apply here.

## Decided

- Module `duckdb_batch.py`, class `DuckDBBatchStore`; the unreleased
  `duckdb_.py` draft is deleted in the same change.
- `close()` drops the store's tables.
- Materialize per view, at view creation; per-query dataset/external filters
  removed.
- Mapping table built from `Linker.mappings()`, dropped after each build;
  `nk_entity_props` replaced by an inline `VALUES` list.
- New `nomenklatura/duck.py` module with three responsibilities: the typed
  statement-relation contract, a `DESCRIBE`-based validation helper (called at
  store init), and DuckDB connection management (memory/thread config,
  generalized from the blocker's inline setup; the blocker migrates onto it in
  this change).

## update() benchmark (decided: no entity_id index)

Measured 2026-08-22 (`contrib/duckdb_store_update_bench.py`, 4M statements /
500k entities / 2000 pairwise merges, in-memory DB): without an `entity_id`
index, updates cost 5.26 ms each (190/s), flat over the run; with the index,
1.50 ms (667/s) plus a 0.18s index build. The no-index cost scales linearly
with table size (a ~127M-row scope extrapolates to ~150–170 ms/update), the
indexed cost stays near-flat but DuckDB ART indexes are memory-resident.
Decision: the scan cost is sustainable — **no second index**; revisit only if
an xref run at full scale shows update() dominating.

## Open questions

1. **View-scope vs store-scope**: view scope must be ⊆ store dataset. Enforce,
   or trust the existing convention (every zavod flow passes the store's own
   dataset)?

## Deferred: live store sketch (for when web-dedupe starts)

Zero-DDL, read-only connection friendly. Point reads via
`entity_id IN (…referents…)` with canonical assigned in Python; `update()` a
true no-op; `get_inverted()` per-call scan with inline entity-props `VALUES`
(documented slow — exporters belong on the batch store); `entities()` either
buffers merged clusters Python-side or is out of scope. Fast point reads require
the relation clustered on `entity_id` — a resolution-independent artifact that
never goes stale, which is the entire point of the mode.
