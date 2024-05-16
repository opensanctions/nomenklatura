import redis
import orjson
from redis.client import Redis, Pipeline
from datetime import datetime, timezone
from typing import Generator, List, Optional, Set, Tuple
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker, Identifier
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.store.util import b, pack_prop, unpack_prop


def pack_statement(stmt: Statement) -> bytes:
    values = (
        stmt.id,
        stmt.entity_id,
        stmt.dataset,
        pack_prop(stmt.schema, stmt.prop),
        stmt.value,
        stmt.lang,
        stmt.original_value,
        stmt.first_seen,
        stmt.last_seen,
        stmt.target,
        stmt.external,
    )
    return orjson.dumps(values)


def unpack_statement(data: bytes, canonical_id: str) -> Statement:
    (
        id,
        entity_id,
        dataset,
        prop_id,
        value,
        lang,
        original_value,
        first_seen,
        last_seen,
        target,
        external,
    ) = orjson.loads(data)
    schema, _, prop = unpack_prop(prop_id)
    return Statement(
        id=id,
        entity_id=entity_id,
        prop=prop,
        schema=schema,
        value=value,
        lang=lang,
        dataset=dataset,
        original_value=original_value,
        first_seen=first_seen,
        last_seen=last_seen,
        target=target,
        canonical_id=canonical_id,
        external=external,
    )


class VersionedRedisStore(Store[DS, CE]):
    def __init__(
        self,
        dataset: DS,
        linker: Linker[CE],
        url: str,
        db: Optional["Redis[bytes]"] = None,
    ):
        super().__init__(dataset, linker)
        self.url = url
        if db is None:
            db = redis.from_url(url, decode_responses=False)
        self.db = db
        # for kvrocks:
        # self.db.config_set("redis-cursor-compatible", "yes")

    def get_latest(self, dataset: str) -> Optional[str]:
        val = self.db.get(b(f"ds:{dataset}:latest"))
        return val.decode("utf-8") if val is not None else None

    def writer(
        self, dataset: Optional[DS], version: Optional[str] = None
    ) -> Writer[DS, CE]:
        if version is None:
            version = datetime.now().replace(tzinfo=timezone.utc).isoformat()
        dataset = dataset or self.dataset
        return VersionedRedisWriter(self, dataset=dataset, version=version)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return VersionedRedisView(self, scope, external=external)

    def close(self) -> None:
        self.db.close()


class VersionedRedisWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 1_000

    def __init__(self, store: VersionedRedisStore[DS, CE], dataset: DS, version: str):
        self.version = version
        self.dataset = dataset
        self.ver = f"{dataset.name}:{version}"
        self.prev = self.store.get_latest(dataset.name)
        self.store: VersionedRedisStore[DS, CE] = store
        self.pipeline: Optional["Pipeline[bytes]"] = None
        self.batch_size = 0

    def flush(self) -> None:
        if self.pipeline is not None:
            self.pipeline.execute()
        self.pipeline = None
        self.batch_size = 0

    def release(self) -> None:
        """Release the current version of the dataset (i.e. tag it as the latest
        version in the relevant lookup key)."""
        ds = self.dataset.name
        self.store.db.set(b(f"ds:{ds}:latest"), b(self.version))
        self.store.db.lpush(b(f"ds:{ds}:history"), b(self.version))

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
        e = Identifier.get(entity_id)
        canonical = self.store.linker.get_canonical(e)
        keys = [f"stmt:{self.ver}:{i}" for i in self.store.linker.connected(e)]
        for v in self.store.db.sunion(keys):
            stmt = unpack_statement(v, canonical)  # type: ignore
            statements.append(stmt)
            datasets.add(stmt.dataset)

            if stmt.prop_type == registry.entity.name:
                vc = self.store.linker.get_canonical(stmt.value)
                self.pipeline.srem(b(f"i:{vc}"), b(entity_id))

        for dataset in datasets:
            self.pipeline.srem(b(f"ds:{dataset}"), b(entity_id))

        return list(statements)


class VersionedRedisView(View[DS, CE]):
    def __init__(
        self, store: VersionedRedisStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: VersionedRedisStore[DS, CE] = store

        # Get the latest version for each dataset in the scope
        vers = [self.store.get_latest(d) for d in scope.leaf_names]
        self.vers: List[str] = [v for v in vers if v is not None]

    def has_entity(self, id: str) -> bool:
        keys = [b(f"stmt:{v}:{id}") for v in self.vers]
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
