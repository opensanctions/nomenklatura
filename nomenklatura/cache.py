import math
import json
import logging
from random import randint
from dataclasses import dataclass
from typing import Any, cast, Dict, Optional, Union, Generator
from datetime import datetime, timedelta
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.exc import OperationalError, InvalidRequestError
from sqlalchemy.dialects.postgresql import insert as upsert

from nomenklatura.dataset import Dataset
from nomenklatura.db import get_engine, get_metadata

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
        self, engine: Engine, metadata: MetaData, dataset: Dataset, create: bool = False
    ) -> None:
        self.dataset = dataset
        self._engine = engine
        self._conn: Optional[Connection] = None
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

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = self._engine.connect()
        return self._conn

    def set(self, key: str, value: Value) -> None:
        self._preload.pop(key, None)
        cache = {
            "timestamp": datetime.utcnow(),
            "key": key,
            "dataset": self.dataset.name,
            "text": value,
        }
        try:
            istmt = upsert(self._table).values([cache])
            values = dict(timestamp=istmt.excluded.timestamp, text=istmt.excluded.text)
            stmt = istmt.on_conflict_do_update(index_elements=["key"], set_=values)
            self.conn.execute(stmt)
        except (OperationalError, InvalidRequestError) as exc:
            log.info("Error while saving to cache: %s" % exc)
            self.reset()

    def set_json(self, key: str, value: Any) -> None:
        return self.set(key, json.dumps(value))

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[Value]:
        if max_age is not None and max_age < 1:
            return None

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
        try:
            result = self.conn.execute(q)
            row = result.fetchone()
        except InvalidRequestError as ire:
            log.warn("Cache fetch error: %s", ire)
            self.reset()
            return None
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
        pq = delete(self._table)
        pq = pq.where(self._table.c.key == key)
        try:
            self.conn.execute(pq)
        except InvalidRequestError as ire:
            log.warn("Cache delete error: %s", ire)
            self.reset()
            return None

    def all(self, like: Optional[str]) -> Generator[CacheValue, None, None]:
        q = select(self._table)
        if like is not None:
            q = q.filter(self._table.c.key.like(like))

        result = self.conn.execute(q)
        for row in result.yield_per(10000):
            yield CacheValue(row.key, row.dataset, row.text, row.timestamp)

    def preload(self, like: Optional[str] = None) -> None:
        log.info("Pre-loading cache: %r", like)
        for cache in self.all(like=like):
            self._preload[cache.key] = cache

    def clear(self) -> None:
        try:
            pq = delete(self._table)
            pq = pq.where(self._table.c.dataset == self.dataset.name)
            self.conn.execute(pq)
        except InvalidRequestError:
            self.reset()
            
    def reset(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn = None

    def flush(self) -> None:
        # log.info("Flushing cache.")
        if self._conn is not None:
            try:
                self._conn.commit()  # type: ignore
            except InvalidRequestError:
                log.info("Transaction was failed, cannot store cache state.")
            self._conn.close()
        self.reset()

    def close(self) -> None:
        self.flush()

    def __repr__(self) -> str:
        return f"<Cache({self._table!r})>"

    def __hash__(self) -> int:
        return hash((self.dataset.name, self._table.name))

    @classmethod
    def make_default(cls, dataset: Dataset) -> "Cache":
        engine = get_engine()
        metadata = get_metadata()
        return cls(engine, metadata, dataset, create=True)
