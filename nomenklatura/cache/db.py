import logging
from dataclasses import dataclass
from typing import cast, Dict, Optional, Generator
from datetime import datetime
from sqlalchemy import MetaData
from sqlalchemy import Table, Column, DateTime, Unicode
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.exc import OperationalError, InvalidRequestError
from sqlalchemy.dialects.postgresql import insert as upsert
from rigour.time import naive_now

from nomenklatura.dataset import Dataset
from nomenklatura.db import get_engine, get_metadata
from nomenklatura.cache.common import Cache, randomize_cache


log = logging.getLogger(__name__)


@dataclass
class CacheValue:
    key: str
    dataset: Optional[str]
    text: Optional[str]
    timestamp: datetime


class DBCache(object):
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

    def set(self, key: str, value: Optional[str]) -> None:
        self._preload.pop(key, None)
        cache = {
            "timestamp": naive_now(),
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

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[str]:
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
        try:
            result = self.conn.execute(q)
            row = result.fetchone()
        except InvalidRequestError as ire:
            log.warning("Cache fetch error: %s", ire)
            self.reset()
            return None
        if row is not None:
            return cast(Optional[str], row.text)
        return None

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

    @classmethod
    def make_default(cls, dataset: Dataset) -> "Cache":
        engine = get_engine()
        metadata = get_metadata()
        return cls(engine, metadata, dataset, create=True)
