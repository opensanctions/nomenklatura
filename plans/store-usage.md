---
description: Requirements zavod's export and validation consumers place on the nomenklatura store
date: 2026-05-15
tags: [store, view, zavod, requirements, consumer-demands]
---

# Consumer demands on the nomenklatura store

This is a **requirements document**, not an API or implementation
proposal. It captures what zavod's read-side consumers in
`zavod/exporters/` and `zavod/validators/__init__.py` actually demand
of the store — observed empirically from the code, framed
independently of the current `View` / `Store` shape so a future
implementation (including a long-lived, network-resident store) can
be evaluated against it.

## Consumer touchpoints in scope

Two callers, both read-only, both running downstream of all writes:

- **`export_data(context, view)`** — iterates `view.entities()` once,
  per-entity calls `feed_unconsolidated` then `consolidate_entity`
  then `feed` on every registered exporter. The view-using exporters
  walk 1-hop adjacency per entity. The delta exporter additionally
  random-accesses entities by ID in its `finish()` phase.
- **`validate_dataset(dataset, view)`** — iterates `view.entities()`
  once, per-entity feeds every validator. Validators do membership
  checks (`has_entity`) and 1-hop adjacency walks.

Both passes run against the same view, in separate `Context` cycles,
within one logical "run."

## Demands

### 1. Sealed scope

Scope is a sealed sub-graph. Every ID returned by any read must
satisfy `has_entity(id) == True`. Concretely:

- `entities()`, `get_entity()`, `has_entity()`, adjacency walks
  (forward and inverse) all agree on the same membership set — no
  skew.
- Adjacency walks filter out neighbours outside scope. The consumer
  never sees a stub neighbour from a dataset not in scope.
- `get_entity(id)` returns `None` *only* for IDs outside scope, never
  for "exists but I'm hiding it."

In the present, scope is `Dataset` (resolving to a set of leaf
dataset names). In the future, scope is expected to extend to
`(dataset, version)` pairs (see `nomenklatura/store/versioned.py`).
The seal must hold against the broader scope tuple, not just dataset
membership.

A consequence: dangling entity references in source data are surfaced
to the consumer as missing-id warnings (today's
`DanglingReferencesValidator`), unambiguously a producer-side data
bug.

### 2. Iteration and ownership

1. **Entities are not owned by the caller.** The store may share or
   cache instances. Consumers that mutate (e.g. consolidation rewrites)
   clone first.
2. **Re-iterability across passes within a run.** Validation iterates
   end-to-end, export iterates end-to-end, both see the same set.
3. **Single-pass within a single consumer pass.** Neither caller
   re-iterates inside its own pass.
4. **No ordering dependency.** Iteration order is unspecified.
   Consumer code treats the stream as a multiset.
5. **No filtering at the iteration boundary.** Consumers receive
   everything and filter inside `feed()`. The `include_schemata`
   parameter exists on today's API but no consumer uses it.
6. **`get_entity(id)` is statement-equivalent to what `entities()`
   would have yielded for the same id.** No object identity required.
7. **No concurrent mutation during a pass.** The data set, version
   pin, and linker state do not change between the start and end of
   a run. Consumers don't defend against this and don't need to.

### 3. Linker / canonical resolution

1. **Canonical resolution happens at retrieval, not in the on-disk
   representation.** The store keeps raw IDs; the read pipeline
   materialises canonical IDs via the pinned linker. This is what
   makes a long-lived store viable across resolver changes — the
   store does not need to be re-linked when the resolver changes.
2. **Consumers only ever see canonical IDs.** Referents are an
   internal concern of the read pipeline. The one consumer-visible
   leak is `entity.extra_referents`, which is intentional.
3. **Cluster fan-out is the store's job.** `entities()` yields one
   entity per canonical cluster; consumers never iterate referents.
4. **Linker calls must be cheap at iteration scale.** Per entity
   yielded, the read pipeline incurs a referent lookup and a
   canonical lookup per entity-typed statement value. At ~1M
   entities × ~5 entity-typed values per entity, that's millions of
   linker calls per pass. The consumer makes no attempt to amortise
   them.
5. **Linker state is pinned for the run.** No mid-run reloads, no
   guards against drift. The delta exporter especially depends on
   this — its hashes are meaningless if canonical IDs shift mid-run.
6. **The write path is linker-agnostic.** Writes record raw IDs and
   raw entity references; only reads apply canonicalisation. This is
   the architectural commitment behind (1).

### 4. Snapshot stability

A long-lived store implies writers can land changes (new dataset
versions, resolver updates) while a read pass is in progress. The
consumer demands snapshot isolation:

1. The view must be pinnable to a `(dataset_versions, linker_state)`
   tuple at construction time. Every read on it honours that pin.
2. The pin spans the entire run — validation pass, export pass, and
   the delta exporter's `finish()` random-access phase all see the
   same snapshot.
3. The pin is selected by the orchestrator (the code that constructs
   the view), not by the consumer code. Exporters and validators
   iterate the view they're handed; they don't think about versions.
4. Concurrent writers landing other versions or other linker states
   in parallel must be invisible to a pinned view.
5. **Eager-built, not on-demand.** The store is populated
   continuously by writers (each crawler builds its own section as
   it runs) and each version is *released* once writing is complete
   — the `release_version` semantics already present in today's
   `VersionedRedisStore`. The consumer's "no build phase" assumption
   depends entirely on the orchestrator selecting a pin over
   already-released versions. There is no consumer-triggered build
   step.

Open: the delta exporter currently backfills the previous snapshot
from disk artefacts (`exporters/delta.py:18`). A long-lived store
could supply that prior snapshot directly via a second pinned view,
retiring `HashDelta`'s disk-backfill path. Whether to add this as a
demand depends on whether delta backfill stays in zavod or moves to
the store.

### 5. Statement-level access

The `feed_unconsolidated` path (`StatementsCSVExporter` only) walks
`entity.statements` per entity:

1. **`entity.statements` is accessible on every entity yielded by
   `entities()`, with no additional store ops.** Statements ride
   along with the entity payload.
2. **`entity.statements` is post-store-consolidation,
   pre-export-consolidation.** Linker canonicalisation and scope
   filtering have been applied (so canonical IDs are baked in); the
   export pipeline's `simplify_names` / `simplify_dates` /
   `simplify_undirected` have not. This line — between read-time
   consolidation (in scope for the store) and export-pipeline
   consolidation (downstream) — must be respected.
3. **The `external` flag is honoured at statement level.** A view
   constructed with `external=False` yields only non-external
   statements through `entity.statements`.
4. **Order within `entity.statements` is unspecified.** Consumers
   don't rely on it.

### 6. The `external` flag

The view's `external` flag is selected by the code that constructs
the view (one layer above exporters/validators). Within the consumer
scope it's an inherited property of the view. The demand: all read
operations — `entities()`, `get_entity()`, `has_entity()`, adjacency
walks, `entity.statements` — honour `external` consistently. No
operation may surface external statements or entities reachable only
through external statements when `external=False`.

### 7. Memory footprint

Per consumer pass, memory is **O(1) in |scope|**, modulo a few
bounded per-pass accumulators (`Statistics` for the exporter and
validator, `HashDelta` for the delta exporter, an optional
small-bounded fragment cache). The store must support iteration
without requiring the consumer to materialise the scope in memory.

This applies to the store implementation too — `entities()` must be
streaming, not "build a full canonical-id map then yield." Today's
`KVStore.entities()` materialises the canonical→source map up-front;
fine at sanctions scale (~648 MB peak in the bench), unacceptable at
enrichment scale (~150M entities). Flag as a known
implementation-side gap against this demand.

## Work budget

Anchored to today's full-database export of ~90 min (rough), of which
~45 min is store-build cost (LevelDB hydration + optimize) and ~45 min
is the retrieval pass. The 45-min number is approximate; for the
purposes of the demands below, treat it as the order-of-magnitude
budget rather than a hard contract.

An eager-built, long-lived store eliminates the build cost from the
consumer's ledger. The retrieval pass therefore has headroom up to
~1.2× today's retrieval (≈54 min) before the business case erodes.

What scales with what, per pass:

| Pass | Work scales with |
| --- | --- |
| Validation | O(\|scope\| × avg outbound entity-typed refs) for membership; O(\|scope\| × avg adjacency degree) for self-reference. |
| Export (entity loop) | O(\|scope\| × adjacency × number of view-using exporters). Adjacency redundancy across exporters is real today; whether it's de-duplicated in the store or in zavod is an implementation choice. |
| Export (`feed_unconsolidated`) | O(Σ statements). |
| Delta finalisation | O(\|delta set\|). |

## Access-pattern ceiling on network-resident stores

The consumer code's dominant access pattern is **random-access per
neighbour**: the export loop's `view.get_adjacent(entity)` fans out
into one `view.get_entity(neighbour)` per neighbour, and the
validation loop's `DanglingReferencesValidator` calls
`view.has_entity(ref)` once per outbound entity-typed reference. At
full-DB scale that produces order-of-magnitude **10⁷–10⁸ random-access
operations per pass**.

For a local store, those ops cost ~15 µs each and the math works. For
a network-resident store at GCP same-AZ pod-to-pod latencies
(~200–500 µs RTT), the math doesn't:

| RTT | 50M ops | 100M ops |
| --- | --- | --- |
| 200 µs | ~2.8 h | ~5.6 h |
| 400 µs | ~5.6 h | ~11.1 h |

**This is fundamental to the access pattern, not the store
implementation.** Every store-side optimisation we've evaluated
(aggregate-hash key layout, dataset-presence index, server-side
scripts) moves per-call cost within a ~2× factor; none can beat the
RTT × N wall. At the access counts above, even an unrealistically
cheap network store (50 µs/call) blows past the 1-hour mark.

Empirical anchor (sanctions collection, 374K entities, localhost
KVRocks vs local LevelDB; see `contrib/store_perf.py`):

| Phase | KV (KVRocks) | LevelDB | KV / Level |
| --- | --- | --- | --- |
| WRITE | 23,078 stmts/s | 46,270 stmts/s | 0.50× |
| READ (entities iteration) | 14,184 ents/s | 41,453 ents/s | 0.34× (KV ~2.9× slower) |
| POINT LOOKUP | 1,750 lookups/s | 64,267 lookups/s | 0.027× (KV ~37× slower) |

`entities()` is "only" ~3× slower because it streams: batched marker
discovery + pipelined `HGETALL` keeps per-entity round-trips low.
`get_entity` is ~37× slower because it must fan out across all
(dataset, version) pairs in scope on every call (85 datasets in the
sanctions scope) and the empty responses still cost wire time. Moving
this to GCP same-AZ RTTs pushes the per-call cost above 700 µs and
the gap to LevelDB widens.

**Consequence for the demands:** a 45-min budget at this RTT regime
requires the consumer's effective network-call count drop from
**O(\|scope\| × adjacency)** to roughly **O(\|scope\|)**. The current
exporters/validators code does not satisfy this. Closing the gap is
an *access-pattern* problem on the consumer side, not a store-design
problem on the implementation side. The implementation guardrails
below remain necessary but are insufficient on their own.

## Implementation guardrails for a network-resident store

A long-lived, network-resident store (Redis-protocol or similar) is
expected to land within the realistic-target band above. The
unavoidable network overheads at OS scale are small: at LAN RTTs,
batched traversal of ~10M entities is a few seconds of pure network
time; bandwidth (~20 GB at typical OS scale) is not a bottleneck.
The demands tighten on *how* the implementation must be shaped to
realise that target — not on whether the network approach is viable.

- **Round-trips are batched, not per-op.** `SSCAN` + pipelined
  `MGET` at batch size ~10²–10³ per network call. Per-entity round
  trips are the failure mode; bulk traversal is the design point.
- **The linker is consumer-local.** `Linker` lives in the consumer
  process; `get_canonical` and `get_referents` never cross the
  network. Putting the linker behind the same network protocol is
  the one design choice that would blow the budget by orders of
  magnitude (millions of canonical lookups per pass).
- **Wire format is compact-binary.** Per-statement text framing at
  hundreds-of-millions scale would dominate; compact packing
  (today's `orjson`-packed tuples or equivalent) is fine.
- **The pin from §4 is mandatory.** Concurrent writes from other
  crawlers are the default state of the system, not the exception.
- **Transient retry is internal to the store client.** The consumer
  holds a view for the duration of the run (~50 min) and treats
  reads as "succeeds or raises a recognisable error." The consumer
  does not manage low-level connection state.
- **Failure model: fatal-with-internal-retry is sufficient today.**
  The current consumer treats a read failure as fatal and dies. This
  remains acceptable so long as internal retry keeps fatals rare. If
  observed failure rates climb high enough that whole-run restarts
  become intolerable, resumable iteration becomes a real demand —
  but it isn't one yet.

## Latent demands (not active today)

- **Validation and export run as two separate iterations of the same
  view.** Nothing structurally forces this. Fusing them into one pass
  roughly halves retrieval work. Today's code does not ask for this.
- **The consumer assumes random-access per neighbour is cheap.** True
  for a local store, untrue for a network store at the scales above.
  Reshaping the consumer's access pattern (fused iteration with
  pre-batched 1-hop neighbourhood, bulk preload to a local
  materialised view, etc.) is required if a network-resident store
  is to fit the budget. The shapes of this demand are not yet locked;
  see the access-pattern discussion accompanying this document.
