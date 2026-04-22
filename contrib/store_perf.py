"""
Benchmark: KVStore (Redis/KVRocks) vs LevelDB store for the sanctions collection.

Usage:
    python contrib/store_perf.py [kv|level|both]

Requires:
    - zavod configured with access to the sanctions archive
    - For kv: Redis running on localhost:6379
    - For level: local disk (uses zavod's default state path)
"""

import sys
import time
import resource

from zavod.logs import get_logger
from zavod.meta import get_catalog, Dataset
from zavod.integration.dedupe import get_dataset_linker
from zavod.runtime.versions import get_latest
from zavod.archive import iter_dataset_statements

log = get_logger("store_perf")

REDIS_URL = "redis://localhost:6379/0"


def fmt_rate(count: int, elapsed: float) -> str:
    return f"{count / elapsed:,.0f}/s" if elapsed > 0 else "n/a"


def mem_mb() -> float:
    """Current RSS in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def count_statements(scope: Dataset) -> int:
    """Count total statements across all leaves (for reference)."""
    total = 0
    for dataset in scope.leaves:
        for _ in iter_dataset_statements(dataset):
            total += 1
    return total


# ── KV Store ────────────────────────────────────────────────────────────────


def bench_kv(scope: Dataset):
    import redis as redis_lib
    from nomenklatura.store.kv import KVStore

    linker = get_dataset_linker(scope)
    db = redis_lib.from_url(REDIS_URL, decode_responses=False)
    # Flush when re-running after key format changes; comment out to reuse data.
    db.flushdb()
    store = KVStore(scope, linker, db=db)

    # ── Write phase ──────────────────────────────────────────────────────
    log.info("=== KV Store: WRITE phase ===")
    total_stmts = 0
    write_start = time.time()

    for dataset in sorted(scope.leaves, key=lambda d: d.name):
        ds_version = get_latest(dataset.name)
        if ds_version is None:
            continue
        version = str(ds_version)

        if store.has_version(dataset.name, version):
            log.info("  skipping (exists)", dataset=dataset.name, version=version)
            continue

        ds_start = time.time()
        ds_count = 0
        with store.writer(dataset=dataset, version=version) as writer:
            for stmt in iter_dataset_statements(dataset):
                writer.add_statement(stmt)
                ds_count += 1
                if ds_count % 500_000 == 0:
                    log.info(
                        "  writing...",
                        dataset=dataset.name,
                        statements=f"{ds_count:,}",
                        rate=fmt_rate(ds_count, time.time() - ds_start),
                    )
        store.release_version(dataset.name, version)
        ds_elapsed = time.time() - ds_start
        total_stmts += ds_count
        log.info(
            "  dataset done.",
            dataset=dataset.name,
            statements=f"{ds_count:,}",
            seconds=f"{ds_elapsed:.1f}",
            rate=fmt_rate(ds_count, ds_elapsed),
        )

    write_elapsed = time.time() - write_start
    log.info(
        "KV WRITE total",
        statements=f"{total_stmts:,}",
        seconds=f"{write_elapsed:.1f}",
        rate=fmt_rate(total_stmts, write_elapsed),
        keys=f"{db.dbsize():,}",
        mem_mb=f"{mem_mb():.0f}",
    )

    # ── Read phase ───────────────────────────────────────────────────────
    log.info("=== KV Store: READ phase (entities iteration) ===")
    view = store.view(scope)
    read_start = time.time()
    count = 0
    for ent in view.entities():
        count += 1
        if count % 10_000 == 0:
            elapsed = time.time() - read_start
            log.info(
                "  iterating...",
                entities=f"{count:,}",
                seconds=f"{elapsed:.1f}",
                rate=fmt_rate(count, elapsed),
            )

    read_elapsed = time.time() - read_start
    log.info(
        "KV READ total",
        entities=f"{count:,}",
        seconds=f"{read_elapsed:.1f}",
        rate=fmt_rate(count, read_elapsed),
        mem_mb=f"{mem_mb():.0f}",
    )

    # ── Point lookups ────────────────────────────────────────────────────
    log.info("=== KV Store: POINT LOOKUP phase ===")
    # Collect some entity IDs to look up
    sample_ids = []
    for idx, ent in enumerate(view.entities()):
        if ent.id is not None:
            sample_ids.append(ent.id)
        if len(sample_ids) >= 1000:
            break

    lookup_start = time.time()
    for eid in sample_ids:
        view.get_entity(eid)
    lookup_elapsed = time.time() - lookup_start
    log.info(
        "KV LOOKUP total",
        lookups=len(sample_ids),
        seconds=f"{lookup_elapsed:.3f}",
        rate=fmt_rate(len(sample_ids), lookup_elapsed),
    )

    return {
        "write_stmts": total_stmts,
        "write_secs": write_elapsed,
        "read_entities": count,
        "read_secs": read_elapsed,
        "lookup_count": len(sample_ids),
        "lookup_secs": lookup_elapsed,
    }


# ── LevelDB Store ──────────────────────────────────────────────────────────


def bench_level(scope: Dataset):
    from zavod.store import get_store

    linker = get_dataset_linker(scope)
    store = get_store(scope, linker)

    # ── Write phase (sync) ───────────────────────────────────────────────
    log.info("=== LevelDB Store: WRITE phase (sync) ===")
    write_start = time.time()
    store.sync(clear=True)
    write_elapsed = time.time() - write_start

    # Count statements for comparison
    total_stmts = 0
    for dataset in scope.leaves:
        for _ in iter_dataset_statements(dataset, external=True):
            total_stmts += 1

    log.info(
        "LevelDB WRITE total",
        statements=f"{total_stmts:,}",
        seconds=f"{write_elapsed:.1f}",
        rate=fmt_rate(total_stmts, write_elapsed),
        mem_mb=f"{mem_mb():.0f}",
    )

    # ── Read phase ───────────────────────────────────────────────────────
    log.info("=== LevelDB Store: READ phase (entities iteration) ===")
    view = store.view(scope)
    read_start = time.time()
    count = 0
    for ent in view.entities():
        count += 1
        if count % 10_000 == 0:
            elapsed = time.time() - read_start
            log.info(
                "  iterating...",
                entities=f"{count:,}",
                seconds=f"{elapsed:.1f}",
                rate=fmt_rate(count, elapsed),
            )

    read_elapsed = time.time() - read_start
    log.info(
        "LevelDB READ total",
        entities=f"{count:,}",
        seconds=f"{read_elapsed:.1f}",
        rate=fmt_rate(count, read_elapsed),
        mem_mb=f"{mem_mb():.0f}",
    )

    # ── Point lookups ────────────────────────────────────────────────────
    log.info("=== LevelDB Store: POINT LOOKUP phase ===")
    sample_ids = []
    for idx, ent in enumerate(view.entities()):
        if ent.id is not None:
            sample_ids.append(ent.id)
        if len(sample_ids) >= 1000:
            break

    lookup_start = time.time()
    for eid in sample_ids:
        view.get_entity(eid)
    lookup_elapsed = time.time() - lookup_start
    log.info(
        "LevelDB LOOKUP total",
        lookups=len(sample_ids),
        seconds=f"{lookup_elapsed:.3f}",
        rate=fmt_rate(len(sample_ids), lookup_elapsed),
    )

    store.close()

    return {
        "write_stmts": total_stmts,
        "write_secs": write_elapsed,
        "read_entities": count,
        "read_secs": read_elapsed,
        "lookup_count": len(sample_ids),
        "lookup_secs": lookup_elapsed,
    }


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    catalog = get_catalog()
    scope = catalog.require("sanctions")

    mode = sys.argv[1] if len(sys.argv) > 1 else "both"

    results = {}
    if mode in ("kv", "both"):
        results["kv"] = bench_kv(scope)
    if mode in ("level", "both"):
        results["level"] = bench_level(scope)

    if len(results) == 2:
        kv = results["kv"]
        lv = results["level"]
        log.info("=" * 60)
        log.info("=== COMPARISON ===")
        log.info(
            "WRITE",
            kv_secs=f"{kv['write_secs']:.1f}",
            level_secs=f"{lv['write_secs']:.1f}",
            ratio=f"{kv['write_secs'] / lv['write_secs']:.2f}x",
        )
        log.info(
            "READ",
            kv_secs=f"{kv['read_secs']:.1f}",
            kv_entities=f"{kv['read_entities']:,}",
            level_secs=f"{lv['read_secs']:.1f}",
            level_entities=f"{lv['read_entities']:,}",
            ratio=f"{kv['read_secs'] / lv['read_secs']:.2f}x",
        )
        log.info(
            "LOOKUP (1000)",
            kv_secs=f"{kv['lookup_secs']:.3f}",
            level_secs=f"{lv['lookup_secs']:.3f}",
            ratio=f"{kv['lookup_secs'] / lv['lookup_secs']:.2f}x",
        )
