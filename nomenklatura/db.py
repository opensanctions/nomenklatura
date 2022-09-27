from contextlib import contextmanager
import os
from pathlib import Path
from functools import cache
from typing import Optional, Generator
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine, Connection

DB_PATH = Path("nomenklatura.db").resolve()
DB_URL = os.environ.get("NOMENKLATURA_DB_URL", f"sqlite:///{DB_PATH.as_posix()}")
Conn = Optional[Connection]


@cache
def get_engine() -> Engine:
    return create_engine(DB_URL)


@cache
def get_metadata() -> MetaData:
    return MetaData(bind=get_engine())


@contextmanager
def ensure_tx(engine: Engine, conn: Conn = None) -> Generator[Connection, None, None]:
    if conn is not None:
        yield conn
        return
    with engine.begin() as conn:
        yield conn
