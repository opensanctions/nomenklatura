---
description: Sketch — nomenklatura as a read-side server (embedded storage, streaming RPC to consumers) to bypass the network access-pattern ceiling and centralise the Resolver
date: 2026-05-16
tags: [permastore, server, resolver, architecture]
---

# Nomenklatura as a read-side server

A note, not a plan. Captures the "server with embedded store" shape
that emerged from pricing the network access-pattern ceiling in
[[store-usage]]. Worth coming back to if/when the access-pattern
reshape becomes load-bearing.

## Why

The KV-permastore retrieval math runs into a wall: the consumer's
O(|scope| × adjacency) random-access pattern costs 10⁷–10⁸ network
ops per full-DB export pass. At GCP same-AZ RTTs (~200–500 µs/op)
that's 3–11 hours, an order of magnitude past the budget. Every
store-side optimisation we evaluated (aggregate-hash layout,
dataset-presence index, server-side scripts) moves per-call cost
within a ~2× factor; none beats `RTT × N`.

To push the budget back into shape without rewriting every
adjacency-using exporter, **collapse N**: replace millions of
independent random-access ops with one long-lived stream from a
server that already has the data local.

## Shape

A **nomenklatura server**: one process that owns the read-side of
the store — traversal, linker, entity assembly — and exposes a
streaming RPC endpoint to consumers.

- Streaming RPC endpoint per pinned view:
  `(scope, dataset_versions, linker_state, external_flag) →` stream
  of fragment events, each carrying the entity plus its 1-hop and
  bounded 2-hop neighbourhood.
- The consumer becomes a thin streaming client. Its outer loop is
  "receive next event, hand to all exporters/validators." No
  view-level random access on the hot path; `view.get_entity` /
  `view.get_adjacent` either disappear or become rare second-class
  RPCs.

### Storage

Two flavours, sharing the same external API:

**Embedded RocksDB (preferred).** The server holds the on-disk store
directly. RocksDB's sorted layout makes the per-(ds, ver) prefix scan
problem trivially cheap — same shape as today's LevelDB store. The
empirical LevelDB baseline from [[store-usage]] (~41K ents/s on full
iteration, ~64K lookups/s on point access) is roughly what this
variant inherits at the storage layer; the network overhead is then
limited to one long-lived stream per consumer rather than per-op.
Concurrent reads are native to RocksDB; writes serialise inside the
engine; view snapshots use RocksDB's `Snapshot` API and ref-counted
SST files, giving snapshot isolation for free against concurrent
writers.

Trade-off: RocksDB is single-process. Horizontal scaling means either
streaming replication (one writer, N read replicas hydrated from a
log), build-per-server-instance from a central source at startup, or
single-instance deployment. Single-instance is likely fine to start
with — matches OS's deployment posture today.

**KVRocks-backed (alternative).** The server fronts KVRocks over a
local UNIX socket. KVRocks is multi-process-friendly and speaks the
Redis protocol, so non-Python clients could in principle reach it
directly. But since the server *is* the consumer API, the
multi-language argument is moot — and the Redis wire protocol adds
~10–30 µs per op of avoidable overhead.

The embedded variant is structurally simpler and faster. The
KVRocks variant is only worth it if multi-process access to the
underlying KV becomes a real requirement for an independent reason.

## Bonus: Resolver centralisation

The `Resolver` / `Linker` consumes significant memory in every
consumer process. OS runs many crawlers in parallel and each
currently loads its own copy. Aggregate footprint across the fleet
is real ops cost.

If the resolver lives in the server:

- Crawler and consumer processes never load the resolver themselves.
  Memory drops to a fixed cost per server, not per process.
- Resolver state can be hot-reloaded centrally when judgements
  change, rather than every consumer re-loading independently.
- The "linker is consumer-local" demand from store-usage.md moves
  one layer: linker is now server-local. Same intent, different
  process boundary.

Caveat worth flagging before treating this as free: any code today
that calls `linker.get_canonical` / `linker.get_referents` in a
hot loop becomes RPC. For occasional lookups (write-side enrichment,
the dedupe TUI) that's fine. For hot loops it'd reintroduce the RTT
problem at a different layer. Audit the call sites before
committing.

## What it changes for consumers

- **zavod export & validation pipelines:** outer loop becomes
  `for fragment in client.stream(scope)`. Exporter `feed()` signature
  shifts to accept the fragment instead of `(entity, view)`.
  `ViewFragment` graduates from a zavod-internal cache to part of
  the server's wire schema.
- **yente:** today reads its own statements; the server shape is a
  natural fit for what yente already does as a service. Possibly a
  consolidation point (see below).
- **dedupe TUI / xref:** read-only access via server; judgement
  writes still go through the resolver write path.
- **crawlers (writers):** the write path is a separate concern from
  the read RPC. With the embedded variant, writers either go through
  a write RPC on the server, or ship pre-built SST files for the
  server to ingest. With the KVRocks variant, writers stay direct to
  KVRocks. Either way: read-time linker lookups in crawler code
  become RPC (see caveat above).

## Projected performance

Forward-looking estimate for a competent single-process Python
implementation with embedded RocksDB, in-memory linker, and a
fragment-streaming API. Numbers are ranges, not commitments — they
exist to sanity-check that the architecture isn't dead on arrival
before anyone invests in building it.

**Per-fragment server-side cost** (fragment = entity + 1-hop forward
+ 1-hop inverse + bounded 2-hop forward):

| Step | Cost |
| --- | --- |
| Stream-scan next entity from RocksDB | ~5–10 µs |
| Linker (canonical + referents) | ~5–15 µs |
| Assemble entity from statements (Python) | ~10–20 µs |
| Walk 1-hop forward + inverse (~5–15 neighbours typical) | ~50–150 µs |
| Walk bounded 2-hop forward | ~50–150 µs |
| Serialise to wire format (msgpack / protobuf) | ~30–80 µs |
| Network write (gRPC streaming, LAN, amortised) | ~10–30 µs |
| **Total** | **~160–450 µs per fragment** |

**Throughput envelope**

- Single-threaded Python: **3K–6K fragments/sec.**
- With GIL releases on C-extension I/O and serialisation:
  **peak 8K–15K fragments/sec.**
- Bandwidth at 5K fragments/sec × ~5 KB/fragment = 25 MB/s. Well
  under 1 Gbps LAN — not the bottleneck.

**Workload projections vs. today's numbers**

| Workload | Today | Projected (mid-range) | Speedup |
| --- | --- | --- | --- |
| Full-DB export | ~45 min build + ~45 min read+export ≈ 90 min | ~16 min (no build, stream at ~5K fragments/sec) | 3–5× |
| Sanctions export | ~95s build + ~14s read+export ≈ 109s | ~75s (build eliminated, slower stream) | ~1.4× (sanctions is build-dominated; gains are bigger at full DB) |
| Web-dedupe random access | n/a (no server today) | ~200–500 µs/RPC, 2K–5K reqs/sec sustained | n/a |
| Matching / yente-style | yente-current | comparable | neutral |

**Sensitivity ranges** (where the estimate could move ±2×):

- **Fragment shape.** Removing the 2-hop bound or adding more
  context per fragment scales the per-fragment cost proportionally.
- **Serialisation choice.** Protobuf > JSON; msgpack > Protobuf for
  nested. ~2× spread.
- **Entity assembly.** `StatementEntity.from_statements` plus FtM
  property handling is the dominant Python cost. Cython or a Rust
  bridge could improve it ~5×.
- **Native rewrite.** A Rust server doing the same work plausibly
  reaches 30K–80K fragments/sec — 5–10× over Python. Door worth
  leaving open if perf ever becomes load-bearing.

**Honest framing.** For OS's scale, a competent Python implementation
**probably gets full-DB export into the 10–20 minute range** vs.
today's 90 min with build (or ~45 min without). For dedupe and web
workloads it's clearly fast enough. The numbers are good enough that
"Python server" isn't dead on arrival on the export hot path — it's
3–5× better than today with the build cost eliminated. The
performance argument doesn't force a native rewrite, though it
remains available as a perf reserve.

## Open questions

- **Wire protocol.** gRPC streams vs. HTTP/2 NDJSON vs. raw TCP.
  Streaming, backpressure, mid-stream resume from a position token,
  multi-view multiplexing. Versioning across server / nomenklatura
  / on-disk store.
- **Operational footprint.** A new stateful service to deploy,
  scale, monitor, and back up. CPU-bound on entity assembly; one
  server serving multiple parallel consumers needs throughput
  budgeting.
- **Auth.** Today consumers have direct DB access. The server needs
  an authentication / authorisation model.
- **Relation to yente.** yente already implements a service-oriented
  read path; the server generalises that. Open question whether
  yente's existing internals can be factored into the server, or
  whether the server is a new layer underneath. Needs a closer look
  at yente's architecture before committing direction.

## Decision deferred

Not building this now. Captured because the access-pattern ceiling
in [[store-usage]] has no other answer that fits the budget at GCP
same-AZ scale, and the resolver-memory point makes it appealing
beyond just retrieval speed.

Revisit when:

- The KV-permastore work is otherwise complete and the
  access-pattern bill is the only remaining gap, or
- Resolver memory across concurrent crawlers becomes a real ops
  problem, or
- yente's architecture next gets revisited and a unifying direction
  would help.
