from contextlib import contextmanager
import os
from pathlib import Path
from functools import cache
from typing import Optional, Generator
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine, Connection

DB_PATH = Path("nomenklatura.db").resolve()
DB_URL = os.environ.get("NOMENKLATURA_DB_URL", f"sqlite:///{DB_PATH.as_posix()}")
POOL_SIZE = int(os.environ.get("NOMENKLATURA_DB_POOL_SIZE", "5"))
Conn = Connection
Connish = Optional[Connection]


@cache
def get_engine() -> Engine:
    return create_engine(DB_URL, pool_size=POOL_SIZE)


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
