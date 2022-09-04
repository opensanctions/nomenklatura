from contextlib import contextmanager
from functools import lru_cache
import os
import math
import json
import logging
from pathlib import Path
from random import randint
from functools import cache
from dataclasses import dataclass
from typing import Any, cast, Dict, Optional, Union, Generator
from datetime import datetime, timedelta
from sqlalchemy import MetaData, create_engine
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.dialects.postgresql import insert as upsert

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
def ensure_tx(conn: Conn = None) -> Generator[Connection, None, None]:
    if conn is not None:
        yield conn
        return
    engine = get_engine()
    with engine.begin() as conn:
        yield conn
