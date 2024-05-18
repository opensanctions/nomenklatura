from redis.client import Redis, Pipeline
from typing import Generator, List, Optional, Set, Tuple
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.kv import get_redis, close_redis, b
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.store.util import pack_statement, unpack_statement


class RedisStore(Store[DS, CE]):
    def __init__(
        self,
        dataset: DS,
        linker: Linker[CE],
        db: Optional["Redis[bytes]"] = None,
    ):
        super().__init__(dataset, linker)
        if db is None:
            db = get_redis()
        self.db = db

    def writer(self) -> Writer[DS, CE]:
        return RedisWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return RedisView(self, scope, external=external)

    def close(self) -> None:
        close_redis()


class RedisWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 100_000

    def __init__(self, store: RedisStore[DS, CE]):
        self.store: RedisStore[DS, CE] = store
        self.pipeline: Optional["Pipeline[bytes]"] = None
        self.batch_size = 0

    def flush(self) -> None:
        if self.pipeline is not None:
            self.pipeline.execute()
        self.pipeline = None
        self.batch_size = 0

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None:
            return
        if self.batch_size >= self.BATCH_STATEMENTS:
            self.flush()
        if self.pipeline is None:
            self.pipeline = self.store.db.pipeline()
        canonical_id = self.store.linker.get_canonical(stmt.entity_id)
        stmt.canonical_id = canonical_id

        self.pipeline.sadd(b(f"ds:{stmt.dataset}"), b(canonical_id))
        key = f"x:{canonical_id}" if stmt.external else f"s:{canonical_id}"
        self.pipeline.sadd(b(key), pack_statement(stmt))
        if stmt.prop_type == registry.entity.name:
            vc = self.store.linker.get_canonical(stmt.value)
            self.pipeline.sadd(b(f"i:{vc}"), b(canonical_id))

        self.batch_size += 1

    def pop(self, entity_id: str) -> List[Statement]:
        if self.batch_size >= self.BATCH_STATEMENTS:
            self.flush()
        if self.pipeline is None:
            self.pipeline = self.store.db.pipeline()
        statements: List[Statement] = []
        datasets: Set[str] = set()
        keys = (f"s:{entity_id}", f"x:{entity_id}")
        for v in self.store.db.sunion(keys):
            stmt = unpack_statement(v, entity_id, False)  # type: ignore
            statements.append(stmt)
            datasets.add(stmt.dataset)

            if stmt.prop_type == registry.entity.name:
                vc = self.store.linker.get_canonical(stmt.value)
                self.pipeline.srem(b(f"i:{vc}"), b(entity_id))

        for dataset in datasets:
            self.pipeline.srem(b(f"ds:{dataset}"), b(entity_id))

        return list(statements)


class RedisView(View[DS, CE]):
    def __init__(
        self, store: RedisStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: RedisStore[DS, CE] = store

    def has_entity(self, id: str) -> bool:
        keys = [b(f"s:{id}")]
        if self.external:
            keys.append(b(f"x:{id}"))
        return self.store.db.exists(*keys) > 0

    def get_entity(self, id: str) -> Optional[CE]:
        statements: List[Statement] = []
        keys = [b(f"s:{id}")]
        if self.external:
            keys.append(b(f"x:{id}"))
        for v in self.store.db.sunion(keys):
            statements.append(unpack_statement(v, id, False))  # type: ignore
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        for v in self.store.db.smembers(b(f"i:{id}")):
            entity = self.get_entity(v.decode("utf-8"))
            if entity is None:
                continue
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
        scope_name = b(f"ds:{self.scope.name}")
        if self.scope.is_collection:
            parts = [b(f"ds:{d}") for d in self.scope.leaf_names]
            self.store.db.sunionstore(scope_name, parts)

        for id in self.store.db.sscan_iter(scope_name):
            entity = self.get_entity(id.decode("utf-8"))
            if entity is not None:
                yield entity
