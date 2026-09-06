import logging
from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager
from functools import cache
from typing import Any, cast

from followthemoney import Statement
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    Table,
    Unicode,
    create_engine,
    delete,
)
from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, CursorResult, Dialect, Engine
from sqlalchemy.sql.expression import Executable

from nomenklatura import settings

Conn = Connection
Connish = Connection | None
KEY_LEN = 255
VALUE_LEN = 65535
# Max rows per INSERT for SQLite to stay under SQLITE_MAX_VARIABLE_NUMBER (32,766).
SQLITE_MAX_VARS = 32766

log = logging.getLogger(__name__)


_ENGINE_CACHE: dict[str, Engine] = {}


def get_engine(url: str | None = None) -> Engine:
    url = url or settings.DB_URL
    engine = _ENGINE_CACHE.get(url)
    if engine is None:
        engine = _make_engine(url)
        _ENGINE_CACHE[url] = engine
    return engine


def _make_engine(url: str) -> Engine:
    connect_args = {}
    if url.startswith("postgres"):
        connect_args["options"] = f"-c statement_timeout={settings.DB_STMT_TIMEOUT}"

    return create_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        connect_args=connect_args,
    )


def close_db(url: str | None = None) -> None:
    if url is None:
        for engine in _ENGINE_CACHE.values():
            engine.dispose()
        _ENGINE_CACHE.clear()
        get_metadata.cache_clear()
    else:
        engine_ = _ENGINE_CACHE.pop(url, None)
        if engine_ is not None:
            engine_.dispose()


@cache
def get_metadata() -> MetaData:
    return MetaData()


def is_postgres(dialect: Dialect) -> bool:
    """Return whether the dialect is PostgreSQL."""
    return dialect.name == "postgresql"


def is_sqlite(dialect: Dialect) -> bool:
    """Return whether the dialect is SQLite."""
    return dialect.name == "sqlite"


def dialect_insert(dialect: Dialect, table: Table) -> PostgreSQLInsert | SQLiteInsert:
    """Build an insert that supports the given database's upsert API.

    Use this instead of `sqlalchemy.insert` wherever an `on_conflict_*` clause is
    needed, since those are dialect extensions rather than part of core SQL.
    """
    if is_sqlite(dialect):
        return sqlite_insert(table)
    if is_postgres(dialect):
        return psql_insert(table)
    raise NotImplementedError(f"Upsert not implemented for dialect {dialect.name}")


class Session:
    """Own a single database connection for one unit of work.

    Use this to give several data-access objects the same commit boundary.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._conn: Connection | None = None

    @property
    def connection(self) -> Connection:
        """Get the connection, checking it out on first use."""
        if self._conn is None:
            self._conn = self.engine.connect()
        return self._conn

    @property
    def dialect(self) -> Dialect:
        return self.engine.dialect

    @property
    def is_postgres(self) -> bool:
        return is_postgres(self.dialect)

    @property
    def is_sqlite(self) -> bool:
        return is_sqlite(self.dialect)

    def execute(self, statement: Executable) -> CursorResult[Any]:
        return self.connection.execute(statement)

    def insert(self, table: Table) -> PostgreSQLInsert | SQLiteInsert:
        """Build an insert that supports the active database's upsert API."""
        return dialect_insert(self.dialect, table)

    def create(self, *tables: Table) -> None:
        """Create the given tables on this session's connection."""
        for table in tables:
            table.create(bind=self.connection, checkfirst=True)

    def checkpoint(self) -> None:
        """Commit the current transaction without releasing the connection."""
        if self._conn is not None:
            self._conn.commit()

    def commit(self) -> None:
        """Commit and return the connection to the pool."""
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def rollback(self) -> None:
        """Roll back the current transaction, leaving the connection open for retry."""
        if self._conn is not None:
            self._conn.rollback()

    def close(self) -> None:
        """Dispose the connection, rolling back any transaction still open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
            self.close()

    def __repr__(self) -> str:
        return f"<Session({self.engine.url!r})>"


def make_session(url: str | None = None) -> Session:
    """Build a unit-of-work session from the shared engine pool."""
    return Session(get_engine(url))


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
        # The metadata object is a process-wide cache (get_metadata), so a
        # second store in one process re-declares the table; keep the first
        # definition instead of raising.
        keep_existing=True,
    )


def insert_statements(
    engine: Engine,
    table: Table,
    dataset_name: str,
    statements: Iterable[Statement],
    batch_size: int = settings.STATEMENT_BATCH,
) -> None:
    dataset_count: int = 0
    is_postgresql = is_postgres(engine.dialect)
    # Built once and re-used for every batch: rows are passed as executemany
    # parameters, so SQLAlchemy compiles the statement only on the first batch.
    # An inline `.values(batch)` clause instead makes each batch a distinct
    # statement, and compiling one costs more than parsing the statements did.
    upsert = dialect_insert(engine.dialect, table).on_conflict_do_nothing(
        index_elements=["id"]
    )
    if not is_postgresql:
        # Bound the parameters per statement, in case the dialect rewrites the
        # executemany into a single multi-row INSERT (as psycopg2 does), which
        # would otherwise exceed SQLITE_MAX_VARIABLE_NUMBER.
        sqlite_max_batch = SQLITE_MAX_VARS // len(table.columns)
        batch_size = min(batch_size, sqlite_max_batch)
    with engine.begin() as conn:
        del_q = delete(table).where(table.c.dataset == dataset_name)
        conn.execute(del_q)
        batch: list[Mapping[str, Any]] = []

        for stmt in statements:
            if is_postgresql:
                # Not to_db_row(): that yields UTC-aware datetimes, which psycopg2
                # sends as timestamptz, and casting those into the naive timestamp
                # columns shifts them by the session TimeZone. The ISO strings are
                # cast literally instead, so a load does not depend on the setting.
                row = cast("dict[str, Any]", stmt.to_dict())
                row["prop_type"] = stmt.prop_type
            else:
                row = stmt.to_db_row()
            batch.append(row)
            dataset_count += 1
            if len(batch) >= batch_size:
                args = (len(batch), dataset_count, dataset_name)
                log.info("Inserting batch %s statements (total: %s) into %r" % args)
                conn.execute(upsert, batch)
                batch = []
        if batch:
            conn.execute(upsert, batch)
        log.info("Load complete: %r (%d total)" % (dataset_name, dataset_count))


# TODO: consider offering a COPY-based loader:
# raw_conn = await conn.get_raw_connection()
# driver_conn: Connection = raw_conn.driver_connection
# result = await driver_conn.copy_records_to_table(
#     stmt_table.name,
#     records=load_data_rows(),
#     columns=COLUMNS,
# )
