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
    MetaData,
    Table,
    Unicode,
    create_engine,
    delete,
)
from sqlalchemy.engine import Connection, CursorResult, Dialect, Engine
from sqlalchemy.sql.expression import Executable
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from nomenklatura import settings

Conn = Connection
Connish = Optional[Connection]
KEY_LEN = 255
VALUE_LEN = 65535
# Max rows per INSERT for SQLite to stay under SQLITE_MAX_VARIABLE_NUMBER (32,766).
SQLITE_MAX_VARS = 32766

log = logging.getLogger(__name__)


_ENGINE_CACHE: Dict[str, Engine] = {}


def get_engine(url: Optional[str] = None) -> Engine:
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


def close_db(url: Optional[str] = None) -> None:
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
    """Whether the given dialect is PostgreSQL.

    The single source of truth for the dialect predicate that gates upserts,
    partial indexes, and other backend-specific SQL across the stack. Use it
    instead of comparing ``dialect.name`` inline — SQLAlchemy reports Postgres
    as ``"postgresql"`` (never ``"postgres"``), and scattered checks had drifted
    into three different spellings of this one question.
    """
    return dialect.name == "postgresql"


def is_sqlite(dialect: Dialect) -> bool:
    """Whether the given dialect is SQLite. See :func:`is_postgres`."""
    return dialect.name == "sqlite"


class Session:
    """A single unit of work over one database connection.

    Hand one to the data-access objects that should share a transaction (Cache,
    Resolver, the stateful zavod tables) so the *owner* of the work — a zavod
    Context, a CLI command — controls one commit boundary, instead of each
    object conjuring and holding its own connection. Runs in SQLAlchemy
    "commit-as-you-go" mode: the first ``execute`` opens a transaction and
    ``checkpoint`` ends it while keeping the connection ready for the next, so a
    long run commits on a frequent cadence and never pins Postgres ``xmin`` for
    hours (the cause of the cache/resolver table bloat in production).

    The session is deliberately domain-blind: it owns connection lifetime and
    dialect, and nothing else. It holds no ``MetaData`` — table definitions are
    a consumer/module concern (a ``Table`` runs on any connection regardless of
    which registry it belongs to). Flushing a consumer's buffers or reloading an
    in-memory graph around a checkpoint is the owner's job, not the session's.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._conn: Optional[Connection] = None

    @property
    def connection(self) -> Connection:
        """The live connection, checked out from the pool on first use."""
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

    def create(self, *tables: Table) -> None:
        """Issue ``CREATE TABLE ... IF NOT EXISTS`` for the given tables.

        Creates whatever ``Table`` objects you hand it on this session's
        connection — independent of which ``MetaData`` they belong to — so the
        DDL rides on the same connection as the rest of the unit of work.
        Assumes the tables have no inter-table foreign keys (true across the
        stack); if that changes, group by metadata and use ``create_all``.
        """
        for table in tables:
            table.create(bind=self.connection, checkfirst=True)

    def checkpoint(self) -> None:
        """Commit the current transaction and keep going on the same connection.

        The cadence primitive: call this periodically through a long run (e.g.
        every N entities) so committed rows become vacuumable and no single
        transaction stays open for the whole run. The next ``execute`` begins a
        fresh transaction automatically; the connection is *not* released.
        """
        if self._conn is not None:
            self._conn.commit()

    def commit(self) -> None:
        """Commit and dispose the connection — the terminal end of the work.

        Use ``checkpoint`` mid-run; use ``commit`` once, when the unit of work
        is finished and the connection should go back to the pool.
        """
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


def make_session(url: Optional[str] = None) -> Session:
    """Build a unit-of-work session, the single entry point for a db handle.

    Reuses the process-wide connection pool (one engine per URL) but hands back
    a fresh session with its own connection, so transaction lifetime is
    explicitly owned by the caller rather than floating in module-level caches.
    """
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
    )


def _upsert_statement_batch(
    dialect: Dialect, conn: Connection, table: Table, batch: List[Mapping[str, Any]]
) -> None:
    """Create an upsert statement for the given table and engine."""
    if is_sqlite(dialect):
        lstmt = sqlite_insert(table).values(batch)
        lstmt = lstmt.on_conflict_do_nothing(index_elements=["id"])
        conn.execute(lstmt)
    elif is_postgres(dialect):
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
    is_postgresql = is_postgres(engine.dialect)
    if not is_postgresql:
        sqlite_max_batch = SQLITE_MAX_VARS // len(table.columns)
        batch_size = min(batch_size, sqlite_max_batch)
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
