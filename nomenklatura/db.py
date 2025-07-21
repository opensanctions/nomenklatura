from contextlib import contextmanager
from functools import cache
from typing import Any, Dict, Generator, Iterable, List, Mapping, Optional, cast
import logging

from followthemoney import Statement
from followthemoney.statement.util import get_prop_type
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Dialect,
    MetaData,
    Table,
    Unicode,
    create_engine,
    delete,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nomenklatura import settings

Conn = Connection
Connish = Optional[Connection]
KEY_LEN = 255
VALUE_LEN = 65535

log = logging.getLogger(__name__)


@cache
def get_engine(url: Optional[str] = None) -> Engine:
    url = url or settings.DB_URL
    connect_args = {}
    if url.startswith("postgres"):
        connect_args["options"] = f"-c statement_timeout={settings.DB_STMT_TIMEOUT}"

    return create_engine(
        url, pool_size=settings.DB_POOL_SIZE, connect_args=connect_args
    )


@cache
def get_metadata() -> MetaData:
    return MetaData()


@contextmanager
def ensure_tx(conn: Connish = None) -> Generator[Connection, None, None]:
    if conn is not None:
        yield conn
        return
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


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
        Column("origin", Unicode(KEY_LEN), index=True),
        Column("lang", Unicode(KEY_LEN), nullable=True),
        Column("external", Boolean, default=False, nullable=False),
        Column("first_seen", DateTime, nullable=True),
        Column("last_seen", DateTime, nullable=True),
    )


def _upsert_statement_batch(
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


def insert_statements(
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
            if is_postgresql:
                row = cast(Dict[str, Any], stmt.to_dict())
                row["prop_type"] = get_prop_type(row["schema"], row["prop"])
            else:
                row = stmt.to_db_row()
            batch.append(row)
            dataset_count += 1
            if len(batch) >= batch_size:
                args = (len(batch), dataset_count, dataset_name)
                log.info("Inserting batch %s statements (total: %s) into %r" % args)
                _upsert_statement_batch(engine.dialect, conn, table, batch)
                batch = []
        if len(batch):
            _upsert_statement_batch(engine.dialect, conn, table, batch)
        log.info("Load complete: %r (%d total)" % (dataset_name, dataset_count))


# TODO: consider offering a COPY-based loader:
# raw_conn = await conn.get_raw_connection()
# driver_conn: Connection = raw_conn.driver_connection
# result = await driver_conn.copy_records_to_table(
#     stmt_table.name,
#     records=load_data_rows(),
#     columns=COLUMNS,
# )
