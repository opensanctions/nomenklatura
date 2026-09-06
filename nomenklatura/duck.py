#
# Shared DuckDB conventions for nomenklatura, the DuckDB counterpart to `nomenklatura.db`.
import logging
import re
from pathlib import Path

import duckdb

from nomenklatura.settings import DUCKDB_MEMORY, DUCKDB_THREADS

log = logging.getLogger(__name__)

DuckDBConfig = dict[str, str | bool | int | float | list[str]]

RELATION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

# The statement relation contract: a producer hands consumers a relation (table,
# view, parquet scan) with exactly these column types. Beyond what DESCRIBE can
# check, producers must guarantee: `id` is unique (deduplicate on it) and never
# NULL, nor are entity_id, schema, prop, value, dataset or external; the seen
# timestamps are naive UTC. Sorting by entity_id and zstd compression are
# recommended for parquet artifacts, not required.
STATEMENT_COLUMNS: dict[str, str] = {
    "id": "VARCHAR",
    "entity_id": "VARCHAR",
    "schema": "VARCHAR",
    "prop": "VARCHAR",
    "value": "VARCHAR",
    "dataset": "VARCHAR",
    "lang": "VARCHAR",
    "original_value": "VARCHAR",
    "origin": "VARCHAR",
    "external": "BOOLEAN",
    "first_seen": "TIMESTAMP",
    "last_seen": "TIMESTAMP",
}


def check_relation_name(relation: str) -> str:
    """Reject relation names that cannot be safely interpolated into SQL.

    Relation names cannot be bound as query parameters, so anything accepting
    a caller-supplied name must pass it through here first."""
    if RELATION_NAME.match(relation) is None:
        raise ValueError(f"Invalid relation name: {relation!r}")
    return relation


def validate_statement_relation(conn: duckdb.DuckDBPyConnection, relation: str) -> None:
    """Check that a relation satisfies the statement contract, or raise.

    Consumers call this before querying so that a mistyped column (a VARCHAR
    timestamp, a text `external` flag) fails at setup instead of corrupting
    reads later; producers can call it to verify their output. Raises
    ValueError listing every missing or mistyped column. Nullability is not
    checked: DESCRIBE cannot report it reliably across tables, views and
    parquet scans."""
    check_relation_name(relation)
    rows = conn.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    types: dict[str, str] = {row[0]: row[1] for row in rows}
    problems: list[str] = []
    for column, expected in STATEMENT_COLUMNS.items():
        actual = types.get(column)
        if actual is None:
            problems.append(f"missing column {column!r} ({expected})")
        elif actual != expected:
            problems.append(f"column {column!r} is {actual}, expected {expected}")
    if len(problems) > 0:
        raise ValueError(
            f"Relation {relation!r} is not a valid statement relation: "
            + "; ".join(problems)
        )


def connect(
    path: Path | str | None = None,
    memory_mb: int | str | None = None,
    threads: int | str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with nomenklatura's tuning applied.

    Connections come with `preserve_insertion_order` disabled to keep large
    imports and CTAS out of memory trouble, the session timezone pinned to
    UTC so TIMESTAMPTZ values never render in the host timezone, and FSST
    string compression disabled so index-scan row fetches stay cheap."""
    config: DuckDBConfig = {
        "preserve_insertion_order": False,
        "python_enable_replacements": False,
    }
    # https://duckdb.org/docs/guides/performance/environment
    # > For ideal performance,
    # > aggregation-heavy workloads require approx. 5 GB memory per thread and
    # > join-heavy workloads require approximately 10 GB memory per thread.
    # > Aim for 5-10 GB memory per thread.
    if memory_mb is None:
        memory_mb = DUCKDB_MEMORY
    if memory_mb is not None:
        config["memory_limit"] = f"{int(memory_mb)}MB"
    # > If you have a limited amount of memory, try to limit the number of threads
    if threads is None:
        threads = DUCKDB_THREADS
    if threads is not None:
        config["threads"] = int(threads)
    database = ":memory:" if path is None else str(path)
    log.info("DuckDB connect %r, config: %r", database, config)
    conn = duckdb.connect(database, config=config)
    # GLOBAL, so that cursor() child sessions inherit the pinned timezone.
    conn.execute("SET GLOBAL TimeZone = 'UTC'")
    # Index scans fetch matching rows one at a time, and decompressing FSST
    # strings per row makes that ~12x slower than the fetch itself. GLOBAL
    # rather than per-statement because updates rewrite rows and the next
    # checkpoint recompresses them under whatever setting is in force then.
    conn.execute("SET GLOBAL disabled_compression_methods = 'fsst'")
    return conn
