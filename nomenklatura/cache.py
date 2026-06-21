import math
import json
import logging
from random import randint
from dataclasses import dataclass
from typing import Any, cast, Dict, Optional, Union, Generator
from datetime import datetime, timedelta
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.dialects.postgresql import insert as upsert
from rigour.time import naive_now
from followthemoney import Dataset

from nomenklatura.db import Session


log = logging.getLogger(__name__)
Value = Union[str, None]


@dataclass
class CacheValue:
    key: str
    dataset: Optional[str]
    text: Value
    timestamp: datetime


def randomize_cache(days: int) -> timedelta:
    min_cache = max(1, math.ceil(days * 0.5))
    max_cache = math.ceil(days * 1.3)
    return timedelta(days=randint(min_cache, max_cache))


class Cache(object):
    def __init__(
        self, session: Session, dataset: Dataset, create: bool = False
    ) -> None:
        self.dataset = dataset
        self._session = session
        self._table = Table(
            "cache",
            MetaData(),
            Column("key", Unicode(), primary_key=True),
            Column("text", Unicode(), nullable=True),
            Column("dataset", Unicode(), nullable=False),
            Column("timestamp", DateTime, index=True),
        )
        if create:
            session.create(self._table)

        self._preload: Dict[str, CacheValue] = {}

    def set(self, key: str, value: Value) -> None:
        self._preload.pop(key, None)
        cache = {
            "timestamp": naive_now(),
            "key": key,
            "dataset": self.dataset.name,
            "text": value,
        }
        istmt = upsert(self._table).values(cache)
        values = dict(
            timestamp=istmt.excluded.timestamp,
            text=istmt.excluded.text,
            dataset=istmt.excluded.dataset,
        )
        stmt = istmt.on_conflict_do_update(index_elements=["key"], set_=values)
        self._session.execute(stmt)

    def set_json(self, key: str, value: Any) -> None:
        return self.set(key, json.dumps(value))

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[Value]:
        if max_age is not None and max_age < 1:
            return None

        cache_cutoff = None
        if max_age is not None:
            cache_cutoff = naive_now() - randomize_cache(max_age)

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
        result = self._session.execute(q)
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
        pq = delete(self._table)
        pq = pq.where(self._table.c.key == key)
        self._session.execute(pq)

    def all(self, like: Optional[str]) -> Generator[CacheValue, None, None]:
        q = select(self._table)
        if like is not None:
            q = q.filter(self._table.c.key.like(like))

        result = self._session.execute(q)
        for row in result.yield_per(10000):
            yield CacheValue(row.key, row.dataset, row.text, row.timestamp)

    def preload(self, like: Optional[str] = None) -> None:
        log.info("Pre-loading cache: %r", like)
        for cache in self.all(like=like):
            self._preload[cache.key] = cache

    def clear(self) -> None:
        pq = delete(self._table)
        pq = pq.where(self._table.c.dataset == self.dataset.name)
        self._session.execute(pq)

    def __repr__(self) -> str:
        return f"<Cache({self._table!r})>"

    def __hash__(self) -> int:
        return hash((self.dataset.name, self._table.name))
