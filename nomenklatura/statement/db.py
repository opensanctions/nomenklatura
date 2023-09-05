import logging
from typing import Any, Iterable, List, Mapping

from sqlalchemy import Boolean, Column, DateTime, MetaData, Table, Unicode
from sqlalchemy import delete
from sqlalchemy.engine import Engine

from nomenklatura import settings
from nomenklatura.statement.statement import Statement
from nomenklatura.db import get_upsert_func

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
        Column("target", Boolean, default=False, nullable=False),
        Column("external", Boolean, default=False, nullable=False),
        Column("first_seen", DateTime, nullable=True),
        Column("last_seen", DateTime, nullable=True),
    )


def insert_dataset(
    engine: Engine,
    table: Table,
    dataset_name: str,
    statements: Iterable[Statement],
    batch_size: int = settings.STATEMENT_BATCH,
) -> None:
    dataset_count: int = 0
    is_postgresql = "postgres" in engine.dialect.name
    insert_func = get_upsert_func(engine)
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
                istmt = insert_func(table).values(batch)
                istmt = istmt.on_conflict_do_nothing(index_elements=["id"])
                conn.execute(istmt)
                batch = []
        if len(batch):
            istmt = insert_func(table).values(batch)
            istmt = istmt.on_conflict_do_nothing(index_elements=["id"])
            conn.execute(istmt)
        log.info("Load complete: %r (%d total)" % (dataset_name, dataset_count))


# TODO: consider offering a COPY-based loader:
# raw_conn = await conn.get_raw_connection()
# driver_conn: Connection = raw_conn.driver_connection
# result = await driver_conn.copy_records_to_table(
#     stmt_table.name,
#     records=load_data_rows(),
#     columns=COLUMNS,
# )
