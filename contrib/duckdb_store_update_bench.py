#!/usr/bin/env python
"""Measure DuckDBBatchStore.update() throughput at xref auto-merge cadence.

Builds a synthetic statement table, materializes a view, then times a stream
of pairwise merges applied via store.update() — once against the store as
implemented (no entity_id index, every UPDATE scans) and once with an ART
index on entity_id added after the build (point updates, but index build and
maintenance cost). The numbers decide whether the statement table should get
a second index; see plans/duckdb-store.md.

Usage:
    python contrib/duckdb_store_update_bench.py [--rows 4000000] [--updates 2000]
"""

import argparse
import time

from followthemoney import Dataset, StatementEntity

from nomenklatura import duck
from nomenklatura.resolver import Linker
from nomenklatura.store.duckdb_batch import DuckDBBatchStore, DuckDBBatchView

DATASET = Dataset.make({"name": "bench", "title": "Bench"})

# One in twenty statements is an entity-typed prop, so the edges table sees
# realistic UPDATE traffic too.
GENERATE_SQL = """
CREATE OR REPLACE TABLE statements AS
SELECT
    'stmt-' || i AS id,
    'ent-' || (i % {entities}) AS entity_id,
    CASE WHEN i % 20 = 0 THEN 'Ownership' ELSE 'Person' END AS "schema",
    CASE WHEN i % 20 = 0 THEN 'owner'
         ELSE (CASE i % 4 WHEN 0 THEN 'name' WHEN 1 THEN 'birthDate'
               WHEN 2 THEN 'nationality' ELSE 'notes' END) END AS prop,
    CASE WHEN i % 20 = 0 THEN 'ent-' || ((i * 7) % {entities})
         ELSE 'value-' || i END AS value,
    'bench' AS dataset,
    CAST(NULL AS VARCHAR) AS lang,
    CAST(NULL AS VARCHAR) AS original_value,
    CAST(NULL AS VARCHAR) AS origin,
    false AS external,
    TIMESTAMP '2024-01-01 00:00:00' AS first_seen,
    TIMESTAMP '2024-06-01 00:00:00' AS last_seen
FROM range({rows}) t(i)
"""


def run_scenario(
    conn: "duck.duckdb.DuckDBPyConnection",
    updates: int,
    entity_id_index: bool,
) -> None:
    label = "entity_id index" if entity_id_index else "no index (as implemented)"
    linker: Linker[StatementEntity] = Linker({})
    start = time.perf_counter()
    store: DuckDBBatchStore[Dataset, StatementEntity] = DuckDBBatchStore(
        DATASET, linker, conn, "statements"
    )
    view = store.default_view()
    build_secs = time.perf_counter() - start
    assert isinstance(view, DuckDBBatchView)

    index_secs = 0.0
    if entity_id_index:
        start = time.perf_counter()
        conn.execute(
            f"CREATE INDEX {view.stmt_table}_entity "
            f"ON {view.stmt_table} (entity_id)"
        )
        index_secs = time.perf_counter() - start

    chunk = max(1, updates // 4)
    timings: list[float] = []
    for k in range(updates):
        left, right = f"ent-{2 * k}", f"ent-{2 * k + 1}"
        canonical = linker.add(left, right)
        start = time.perf_counter()
        store.update(canonical)
        timings.append(time.perf_counter() - start)
        if (k + 1) % chunk == 0:
            window = timings[-chunk:]
            print(
                f"    updates {k + 1 - chunk}..{k + 1}: "
                f"{sum(window) / len(window) * 1000:.2f} ms/update"
            )

    total = sum(timings)
    print(f"  [{label}]")
    print(f"    view build: {build_secs:.2f}s" + (
        f", entity_id index build: {index_secs:.2f}s" if entity_id_index else ""
    ))
    print(
        f"    {updates} updates in {total:.2f}s — "
        f"{total / updates * 1000:.2f} ms/update, {updates / total:.0f} updates/s"
    )
    store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=4_000_000)
    parser.add_argument("--updates", type=int, default=2_000)
    args = parser.parse_args()
    entities = max(1, args.rows // 8)

    conn = duck.connect()
    print(f"Generating {args.rows} statements across {entities} entities...")
    conn.execute(GENERATE_SQL.format(rows=args.rows, entities=entities))

    for entity_id_index in (False, True):
        run_scenario(conn, args.updates, entity_id_index)


if __name__ == "__main__":
    main()
