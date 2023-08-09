import os
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from typing import Generator, Optional, Union

from sqlalchemy import MetaData, create_engine
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import Table

from nomenklatura.statement import make_statement_table

DB_PATH = Path("nomenklatura.db").resolve()
DB_URL = os.environ.get("NOMENKLATURA_DB_URL", f"sqlite:///{DB_PATH.as_posix()}")
DB_STORE_TABLE = os.environ.get("NOMENKLATURA_DB_STORE_TABLE", "nk_store")
POOL_SIZE = int(os.environ.get("NOMENKLATURA_DB_POOL_SIZE", "5"))
Conn = Connection
Connish = Optional[Connection]


@cache
def get_engine() -> Engine:
    return create_engine(DB_URL, pool_size=POOL_SIZE)


@cache
def get_metadata() -> MetaData:
    return MetaData()


@cache
def get_statement_table() -> Table:
    return make_statement_table(get_metadata(), DB_STORE_TABLE)


@contextmanager
def ensure_tx(conn: Connish = None) -> Generator[Connection, None, None]:
    try:
        if conn is not None:
            yield conn
        else:
            engine = get_engine()
            with engine.begin() as conn:
                yield conn
    finally:
        if conn is not None:
            conn.commit()


@cache
def get_upsert_func(
    engine: Engine,
) -> Union[sqlite_insert, mysql_insert, psql_insert]:
    if engine.name == "sqlite":
        return sqlite_insert
    if engine.name == "mysql":
        return mysql_insert
    return psql_insert
