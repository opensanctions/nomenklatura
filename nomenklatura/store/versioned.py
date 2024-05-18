import orjson
from redis.client import Redis
from datetime import datetime, timezone
from typing import Generator, List, Optional, Set, Tuple, Dict
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.kv import b, bv, get_redis, close_redis
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker, Identifier, StrIdent
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.util import pack_prop, unpack_prop


def _pack_statement(stmt: Statement) -> bytes:
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


def _unpack_statement(data: bytes, canonical_id: Optional[str] = None) -> Statement:
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
        canonical_id=canonical_id or entity_id,
        external=external,
    )


class VersionedRedisStore(Store[DS, CE]):
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

    def get_latest(self, dataset: str) -> Optional[str]:
        val = self.db.get(b(f"ds:{dataset}:latest"))
        return val.decode("utf-8") if val is not None else None

    def writer(
        self, dataset: Optional[DS] = None, version: Optional[str] = None
    ) -> "VersionedRedisWriter[DS, CE]":
        if version is None:
            version = datetime.now().replace(tzinfo=timezone.utc).isoformat()
        dataset = dataset or self.dataset
        return VersionedRedisWriter(self, dataset=dataset, version=version)

    def view(self, scope: DS, external: bool = False) -> "VersionedRedisView[DS, CE]":
        return VersionedRedisView(self, scope, external=external)

    def update(self, id: StrIdent) -> None:
        # Noop because the VersionedStore is not resolved.
        return

    def close(self) -> None:
        close_redis()


class VersionedRedisWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 2_000

    def __init__(self, store: VersionedRedisStore[DS, CE], dataset: DS, version: str):
        self.version = version
        self.dataset = dataset
        self.ver = f"{dataset.name}:{version}"
        self.store: VersionedRedisStore[DS, CE] = store
        self.prev = store.get_latest(dataset.name)
        self.buffer: List[Statement] = []

    def __enter__(self) -> "VersionedRedisWriter[DS, CE]":
        return self

    def flush(self) -> None:
        db = self.store.db
        pipeline = db.pipeline()

        statements: Dict[str, Set[Statement]] = {}
        for stmt in self.buffer:
            if stmt.entity_id not in statements:
                statements[stmt.entity_id] = set()
            statements[stmt.entity_id].add(stmt)

        # Merge with previous version to get accurate first_seen timestamps
        if self.prev:
            keys = [b(f"stmt:{self.prev}:{e}") for e in statements.keys()]
            for v in db.sunion(keys):
                pstmt = _unpack_statement(bv(v))
                for stmt in self.buffer:
                    if pstmt.id == stmt.id:
                        stmt.first_seen = pstmt.first_seen
                        break

        for entity_id, stmts in statements.items():
            b_entity_id = b(entity_id)
            pipeline.sadd(b(f"ents:{self.ver}"), b_entity_id)
            values = [_pack_statement(s) for s in stmts]
            pipeline.sadd(f"stmt:{self.ver}:{entity_id}", *values)

            for stmt in stmts:
                if stmt.prop_type == registry.entity.name:
                    pipeline.sadd(b(f"inv:{self.ver}:{stmt.value}"), b_entity_id)

        pipeline.execute()
        self.buffer = []

    def release(self) -> None:
        """Release the current version of the dataset (i.e. tag it as the latest
        version in the relevant lookup key)."""
        ds = self.dataset.name
        self.store.db.set(b(f"ds:{ds}:latest"), b(self.version))
        self.store.db.lpush(b(f"ds:{ds}:history"), b(self.version))

    def close(self) -> None:
        self.release()
        self.store.close()

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None:
            return
        self.buffer.append(stmt)
        if len(self.buffer) >= self.BATCH_STATEMENTS:
            self.flush()

    def pop(self, entity_id: str) -> List[Statement]:
        raise NotImplementedError()


class VersionedRedisView(View[DS, CE]):
    def __init__(
        self, store: VersionedRedisStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: VersionedRedisStore[DS, CE] = store

        # Get the latest version for each dataset in the scope
        vers = [(d, self.store.get_latest(d)) for d in scope.leaf_names]
        self.vers: List[Tuple[str, str]] = [(d, v) for d, v in vers if v is not None]

    def _get_stmt_keys(self, entity_id: str) -> List[str]:
        keys: List[str] = []
        ident = Identifier.get(entity_id)
        for id in self.store.linker.connected(ident):
            keys.extend([f"stmt:{d}:{v}:{id}" for d, v in self.vers])
        return keys

    def has_entity(self, id: str) -> bool:
        for key in self._get_stmt_keys(id):
            if self.store.db.scard(key) > 0:
                return True
        return False
        # return self.store.db.exists(*self._get_stmt_keys(id)) > 0

    def get_entity(self, id: str) -> Optional[CE]:
        statements: List[Statement] = []
        keys = self._get_stmt_keys(id)
        if len(keys) == 0:
            return None
        elif len(keys) == 1:
            stmts = self.store.db.smembers(keys[0])
        else:
            stmts = {bv(s) for s in self.store.db.sunion(keys)}
        for v in stmts:
            stmt = _unpack_statement(bv(v), id)
            if not stmt.external or self.external:
                stmt.canonical_id = self.store.linker.get_canonical(stmt.entity_id)
                if stmt.prop_type == registry.entity.name:
                    stmt.value = self.store.linker.get_canonical(stmt.value)
                statements.append(stmt)
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        keys: List[str] = []
        ident = Identifier.get(id)
        for ent_id in self.store.linker.connected(ident):
            keys.extend([f"inv:{d}:{v}:{ent_id}" for d, v in self.vers])
        entities: Set[str] = set()
        refs = (
            {bv(v) for v in self.store.db.sunion(keys)}
            if len(keys) > 0
            else self.store.db.smembers(keys[0])
        )
        for v in refs:
            entity_id = v.decode("utf-8")
            entities.add(self.store.linker.get_canonical(entity_id))
        for entity_id in entities:
            entity = self.get_entity(entity_id)
            if entity is None:
                continue
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
        if len(self.vers) == 0:
            return
        if len(self.vers) == 1:
            scope_name = b(f"ents:{self.vers[0][0]}:{self.vers[0][1]}")
        if len(self.vers) > 1:
            version = max((v for _, v in self.vers), default="latest")
            scope_name = b(f"ents:{self.scope.name}:{version}")
            parts = [b(f"ents:{d}:{v}") for d, v in self.vers]
            self.store.db.sunionstore(scope_name, parts)

        # Keep track of canonical entities to avoid yielding the same
        # de-duplicated entity multiple times. This intrinsically leaks
        # memory, so we're being careful to only record entity IDs
        # that are part of a cluster with more than one ID.
        seen: Set[str] = set()
        for id in self.store.db.sscan_iter(scope_name):
            entity_id = id.decode("utf-8")
            ident = Identifier.get(entity_id)
            connected = self.store.linker.connected(ident)
            if len(connected) > 1:
                canonical_id = max(connected).id
                if canonical_id in seen:
                    continue
                seen.add(canonical_id)
            entity = self.get_entity(entity_id)
            if entity is not None:
                yield entity
