import logging
from typing import Any, Iterable, List, Mapping

from sqlalchemy import delete, Connection, Dialect, Table
from sqlalchemy import Boolean, Column, DateTime, MetaData, Unicode
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nomenklatura import settings
from nomenklatura.statement.statement import Statement

log = logging.getLogger(__name__)
KEY_LEN = 255
VALUE_LEN = 65535


def make_statement_table(
    metadata: MetaData,
    name: str = settings.STATEMENT_TABLE,
) -> Table:
    return Table(
        name,
        metadata,
        Column("id", Unicode(KEY_LEN), primary_key=True, unique=True),
        Column("entity_id", Unicode(KEY_LEN), index=True, nullable=False),
        Column("canonical_id", Unicode(KEY_LEN), index=True, nullable=False),
        Column("prop", Unicode(KEY_LEN), index=True, nullable=False),
        Column("prop_type", Unicode(KEY_LEN), index=True, nullable=False),
        Column("schema", Unicode(KEY_LEN), index=True, nullable=False),
        Column("value", Unicode(VALUE_LEN), nullable=False),
        Column("original_value", Unicode(VALUE_LEN), nullable=True),
        Column("dataset", Unicode(KEY_LEN), index=True),
        Column("lang", Unicode(KEY_LEN), nullable=True),
        Column("external", Boolean, default=False, nullable=False),
        Column("first_seen", DateTime, nullable=True),
        Column("last_seen", DateTime, nullable=True),
    )


def _upsert_batch(
    dialect: Dialect, conn: Connection, table: Table, batch: List[Mapping[str, Any]]
) -> None:
    """Create an upsert statement for the given table and engine."""
    if dialect.name == "sqlite":
        lstmt = sqlite_insert(table).values(batch)
        lstmt = lstmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(lstmt)
    elif dialect.name in ("postgresql", "postgres"):
        pstmt = psql_insert(table).values(batch)
        pstmt = pstmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(pstmt)
    else:
        raise NotImplementedError(f"Upsert not implemented for dialect {dialect.name}")


def insert_dataset(
    engine: Engine,
    table: Table,
    dataset_name: str,
    statements: Iterable[Statement],
    batch_size: int = settings.STATEMENT_BATCH,
) -> None:
    dataset_count: int = 0
    is_postgresql = "postgres" in engine.dialect.name
    with engine.begin() as conn:
        del_q = delete(table).where(table.c.dataset == dataset_name)
        conn.execute(del_q)
        batch: List[Mapping[str, Any]] = []

        for stmt in statements:
            row = stmt.to_dict() if is_postgresql else stmt.to_db_row()
            batch.append(row)
            dataset_count += 1
            if len(batch) >= batch_size:
                args = (len(batch), dataset_count, dataset_name)
                log.info("Inserting batch %s statements (total: %s) into %r" % args)
                _upsert_batch(engine.dialect, conn, table, batch)
                batch = []
        if len(batch):
            _upsert_batch(engine.dialect, conn, table, batch)
        log.info("Load complete: %r (%d total)" % (dataset_name, dataset_count))


# TODO: consider offering a COPY-based loader:
# raw_conn = await conn.get_raw_connection()
# driver_conn: Connection = raw_conn.driver_connection
# result = await driver_conn.copy_records_to_table(
#     stmt_table.name,
#     records=load_data_rows(),
#     columns=COLUMNS,
# )
