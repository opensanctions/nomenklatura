import os
import math
import json
import logging
from pathlib import Path
from random import randint
from dataclasses import dataclass
from typing import Any, cast, Dict, Optional, Union, Generator
from datetime import datetime, timedelta
from sqlalchemy import MetaData, create_engine
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.engine import Engine
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.dialects.postgresql import insert as upsert

from nomenklatura.dataset import DS

log = logging.getLogger(__name__)
Value = Union[str, None]


@dataclass
class CacheValue:
    key: str
    dataset: Optional[str]
    text: Value
    timestamp: datetime


def randomize_cache(days: int) -> timedelta:
    min_cache = max(1, math.ceil(days * 0.7))
    max_cache = math.ceil(days * 1.3)
    return timedelta(days=randint(min_cache, max_cache))


class Cache(object):
    CACHE_PATH = os.environ.get("NOMENKLATURA_CACHE_PATH", ".nk_cache.db")

    def __init__(
        self, engine: Engine, metadata: MetaData, dataset: DS, create: bool = False
    ) -> None:
        self.dataset = dataset
        self._engine = engine
        self._table = Table(
            "cache",
            metadata,
            Column("key", Unicode(), index=True, nullable=False, unique=True),
            Column("text", Unicode(), nullable=True),
            Column("dataset", Unicode(), nullable=False),
            Column("timestamp", DateTime, index=True),
            extend_existing=True,
        )
        if create:
            metadata.create_all(checkfirst=True)

        self._preload: Dict[str, CacheValue] = {}

    def set(self, key: str, value: Value) -> None:
        cache = {
            "timestamp": datetime.utcnow(),
            "key": key,
            "dataset": self.dataset.name,
            "text": value,
        }

        istmt = upsert(self._table).values([cache])
        values = dict(timestamp=istmt.excluded.timestamp, text=istmt.excluded.text)
        stmt = istmt.on_conflict_do_update(index_elements=["key"], set_=values)
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def set_json(self, key: str, value: Any) -> None:
        return self.set(key, json.dumps(value))

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[Value]:
        cache_cutoff = None
        if max_age is not None:
            cache_cutoff = datetime.utcnow() - randomize_cache(max_age)

        cache = self._preload.get(key)
        if cache is not None:
            if cache_cutoff is not None and cache.timestamp < cache_cutoff:
                return None
            return cache.text

        q = select(self._table.c.text)
        q = q.filter(self._table.c.key == key)
        if cache_cutoff is not None:
            q = q.filter(self._table.c.timestamp > cache_cutoff)
        q = q.order_by(self._table.c.timestamp.desc())
        q = q.limit(1)
        with self._engine.connect() as conn:
            result = conn.execute(q)
            row = result.fetchone()
            if row is not None:
                return cast(Optional[str], row.text)
        return None

    def get_json(self, key: str, max_age: Optional[int] = None) -> Optional[Any]:
        text = self.get(key, max_age=max_age)
        if text is None:
            return None
        return json.loads(text)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        self._preload.pop(key, None)
        with self._engine.begin() as conn:
            pq = delete(self._table)
            pq = pq.where(self._table.c.key == key)
            conn.execute(pq)

    def all(self, like: Optional[str]) -> Generator[CacheValue, None, None]:
        q = select(self._table)
        if like is not None:
            q = q.filter(self._table.c.key.like(like))

        with self._engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(q)
            for row in result:
                yield CacheValue(row.key, row.dataset, row.text, row.timestamp)

    def preload(self, like: Optional[str] = None) -> None:
        log.info("Pre-loading cache: %r", like)
        for cache in self.all(like=like):
            self._preload[cache.key] = cache

    def clear(self) -> None:
        with self._engine.begin() as conn:
            pq = delete(self._table)
            pq = pq.where(self._table.c.dataset == self.dataset.name)
            conn.execute(pq)

    def close(self) -> None:
        self._engine.dispose()

    def __repr__(self) -> str:
        return f"<Cache({self._engine.url!r})>"

    def __hash__(self) -> int:
        return hash((self._engine, self._table.name))

    @classmethod
    def make_default(cls, dataset: DS) -> "Cache":
        path = Path(cls.CACHE_PATH).resolve()
        db_uri = f"sqlite:///{path.as_posix()}"
        engine = create_engine(db_uri)
        metadata = MetaData(bind=engine)
        return cls(engine, metadata, dataset, create=True)
