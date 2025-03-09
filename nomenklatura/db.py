from contextlib import contextmanager
from functools import cache
from typing import Generator, Optional, Union
import logging

from sqlalchemy import MetaData, create_engine
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from nomenklatura import settings

Conn = Connection
Connish = Optional[Connection]

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


def get_upsert_func(
    engine: Engine,
) -> Union[sqlite_insert, mysql_insert, psql_insert]:
    if engine.dialect.name == "sqlite":
        return sqlite_insert
    if engine.dialect.name == "mysql":
        return mysql_insert
    if engine.dialect.name in ("postgresql", "postgres"):
        return psql_insert
    raise RuntimeError("Unsupported database engine: %s" % engine.dialect.name)
