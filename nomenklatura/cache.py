import math
import json
import logging
from random import randint
from dataclasses import dataclass
from typing import Any, cast, Dict, Optional, Union, Generator
from datetime import datetime, timedelta
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.engine import Engine
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.dialects.postgresql import insert as upsert

from nomenklatura.dataset import DS
from nomenklatura.db import get_engine, get_metadata
from nomenklatura.db import Connish, Conn, ensure_tx

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
    def __init__(
        self, engine: Engine, metadata: MetaData, dataset: DS, create: bool = False
    ) -> None:
        self.dataset = dataset
        self._table = Table(
            "cache",
            metadata,
            Column("key", Unicode(), primary_key=True),
            Column("text", Unicode(), nullable=True),
            Column("dataset", Unicode(), nullable=False),
            Column("timestamp", DateTime, index=True),
            extend_existing=True,
        )
        if create:
            metadata.create_all(bind=engine, checkfirst=True)

        self._preload: Dict[str, CacheValue] = {}

    def set(self, key: str, value: Value, conn: Connish = None) -> None:
        cache = {
            "timestamp": datetime.utcnow(),
            "key": key,
            "dataset": self.dataset.name,
            "text": value,
        }
        istmt = upsert(self._table).values([cache])
        values = dict(timestamp=istmt.excluded.timestamp, text=istmt.excluded.text)
        stmt = istmt.on_conflict_do_update(index_elements=["key"], set_=values)
        with ensure_tx(conn) as conn:
            conn.execute(stmt)

    def set_json(self, key: str, value: Any, conn: Connish = None) -> None:
        return self.set(key, json.dumps(value), conn=conn)

    def get(
        self, key: str, max_age: Optional[int] = None, conn: Connish = None
    ) -> Optional[Value]:
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
        with ensure_tx(conn) as conn:
            result = conn.execute(q)
            row = result.fetchone()
            if row is not None:
                return cast(Optional[str], row.text)
        return None

    def get_json(
        self, key: str, max_age: Optional[int] = None, conn: Connish = None
    ) -> Optional[Any]:
        text = self.get(key, max_age=max_age, conn=conn)
        if text is None:
            return None
        return json.loads(text)

    def has(self, key: str, conn: Connish = None) -> bool:
        return self.get(key, conn=conn) is not None

    def delete(self, key: str, conn: Connish = None) -> None:
        self._preload.pop(key, None)
        with ensure_tx(conn) as conn:
            pq = delete(self._table)
            pq = pq.where(self._table.c.key == key)
            conn.execute(pq)

    def all(
        self, like: Optional[str], conn: Connish = None
    ) -> Generator[CacheValue, None, None]:
        q = select(self._table)
        if like is not None:
            q = q.filter(self._table.c.key.like(like))

        with ensure_tx(conn) as conn:
            result = conn.execute(q)
            for row in result.yield_per(10000):
                yield CacheValue(row.key, row.dataset, row.text, row.timestamp)

    def preload(self, like: Optional[str] = None, conn: Connish = None) -> None:
        log.info("Pre-loading cache: %r", like)
        for cache in self.all(like=like, conn=conn):
            self._preload[cache.key] = cache

    def clear(self, conn: Connish = None) -> None:
        pq = delete(self._table)
        pq = pq.where(self._table.c.dataset == self.dataset.name)
        with ensure_tx(conn) as conn:
            conn.execute(pq)

    def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<Cache({self._table!r})>"

    def __hash__(self) -> int:
        return hash((self.dataset.name, self._table.name))

    @classmethod
    def make_default(cls, dataset: DS) -> "Cache":
        engine = get_engine()
        metadata = get_metadata()
        return cls(engine, metadata, dataset, create=True)


class ConnCache(Cache):
    def __init__(self, cache: Cache, conn: Conn) -> None:
        self.cache = cache
        self.conn = conn

    def set(self, key: str, value: Value, conn: Connish = None) -> None:
        return self.cache.set(key, value, conn=conn or self.conn)

    def set_json(self, key: str, value: Any, conn: Connish = None) -> None:
        return self.cache.set_json(key, value, conn=conn or self.conn)

    def get(
        self, key: str, max_age: Optional[int] = None, conn: Connish = None
    ) -> Optional[Value]:
        return self.cache.get(key, max_age=max_age, conn=conn or self.conn)

    def get_json(
        self, key: str, max_age: Optional[int] = None, conn: Connish = None
    ) -> Optional[Any]:
        return self.cache.get_json(key, max_age=max_age, conn=conn or self.conn)

    def has(self, key: str, conn: Connish = None) -> bool:
        return self.cache.has(key, conn=conn or self.conn)

    def delete(self, key: str, conn: Connish = None) -> None:
        self.cache.delete(key, conn=conn or self.conn)

    def all(
        self, like: Optional[str], conn: Connish = None
    ) -> Generator[CacheValue, None, None]:
        yield from self.cache.all(like, conn=conn or self.conn)

    def preload(self, like: Optional[str] = None, conn: Connish = None) -> None:
        self.cache.preload(like, conn=conn or self.conn)

    def clear(self, conn: Connish = None) -> None:
        self.cache.clear(conn=conn or self.conn)

    def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<ConnCache({self.conn!r}, {self.cache._table!r})>"

    def __hash__(self) -> int:
        return hash(self.cache)

    @classmethod
    def make_default(cls, dataset: DS) -> "Cache":
        raise NotImplemented
