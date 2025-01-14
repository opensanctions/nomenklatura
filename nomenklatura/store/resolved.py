import orjson
import logging
from redis.client import Redis
from typing import Generator, List, Optional, Tuple
from followthemoney.property import Property
from followthemoney.types import registry
from rigour.env import ENCODING as ENC

from nomenklatura.kv import get_redis, close_redis
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker, StrIdent
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer

log = logging.getLogger(__name__)


class ResolvedStore(Store[DS, CE]):
    """A store implementation which is built to store fully resolved entities. This
    implementation is not designed to be updated, and cannot store individual statements."""

    def __init__(
        self,
        dataset: DS,
        linker: Linker[CE],
        prefix: Optional[str] = None,
        db: Optional["Redis[bytes]"] = None,
    ):
        super().__init__(dataset, linker)
        if db is None:
            db = get_redis()
        self.db = db
        self.prefix = f"xre:{prefix or dataset.name}"

    def writer(self) -> Writer[DS, CE]:
        return ResolvedWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        if external:
            raise NotImplementedError("External views not supported!")
        return ResolvedView(self, scope, external=external)

    def update(self, id: StrIdent) -> None:
        raise NotImplementedError("Entity store cannot update entities")

    def assemble(self, statements: List[Statement]) -> Optional[CE]:
        # This is simplified because the store is considered to be fully resolved
        if not len(statements):
            return None
        return self.entity_class.from_statements(self.dataset, statements)

    def drop(self, prefix: Optional[str] = None) -> None:
        """Delete all data associated with a prefix of the store."""
        pipeline = self.db.pipeline()
        prefix = f"xre:{prefix}" if prefix else self.prefix
        cmds = 0
        for key in self.db.scan_iter(f"{prefix}:*"):
            pipeline.delete(key)
            cmds += 1
            if cmds > 10_000:
                pipeline.execute()
                pipeline = self.db.pipeline()
                cmds = 0
        if cmds > 0:
            pipeline.execute()

    def derive(self, store: Store[DS, CE]) -> None:
        """Copy all data from another store into this one."""
        writer = self.writer()
        view = store.default_view()
        for idx, entity in enumerate(view.entities()):
            if idx > 0 and idx % 10_000 == 0:
                log.info("Deriving resolved store %s: %s...", store.dataset.name, idx)
            writer.add_entity(entity)
        writer.flush()

    def close(self) -> None:
        close_redis()


class ResolvedWriter(Writer[DS, CE]):
    BATCH_ENTITIES = 1_000

    def __init__(self, store: ResolvedStore[DS, CE]):
        self.store: ResolvedStore[DS, CE] = store
        self.entities: List[CE] = []

    def flush(self) -> None:
        pipeline = self.store.db.pipeline()
        for entity in self.entities:
            stmts = []
            for stmt in entity.statements:
                row = (
                    stmt.id,
                    stmt.entity_id,
                    stmt.prop,
                    stmt.schema,
                    stmt.value,
                    stmt.dataset,
                    stmt.lang,
                    stmt.original_value,
                    # stmt.external,
                    stmt.first_seen,
                    stmt.last_seen,
                )
                stmts.append(row)
            obj = {"i": entity.id, "c": entity.caption, "s": stmts}
            key = f"{self.store.prefix}:e:{entity.id}"
            pipeline.set(key.encode(ENC), orjson.dumps(obj))
            for inv_id in entity.get_type_values(registry.entity, matchable=True):
                inv_key = f"{self.store.prefix}:i:{inv_id}"
                pipeline.sadd(inv_key.encode(ENC), key)
        pipeline.execute()
        self.entities = []

    def add_statement(self, stmt: Statement) -> None:
        raise NotImplementedError("Entity store cannot add invididual statements")

    def add_entity(self, entity: CE) -> None:
        self.entities.append(entity)
        if len(self.entities) >= self.BATCH_ENTITIES:
            self.flush()

    def pop(self, entity_id: str) -> List[Statement]:
        raise NotImplementedError("Entity store cannot pop entities")


class ResolvedView(View[DS, CE]):
    def __init__(
        self, store: ResolvedStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: ResolvedStore[DS, CE] = store

    def has_entity(self, id: str) -> bool:
        key = f"{self.store.prefix}:e:{id}"
        return self.store.db.exists(key) > 0

    def _unpack(self, data: bytes) -> CE:
        obj = orjson.loads(data)
        statements: List[Statement] = []
        for stmt in obj["s"]:
            (
                stmt_id,
                entity_id,
                prop,
                schema,
                value,
                dataset,
                lang,
                original_value,
                # external,
                first_seen,
                last_seen,
            ) = stmt
            statements.append(
                Statement(
                    id=stmt_id,
                    entity_id=entity_id,
                    canonical_id=obj["i"],
                    prop=prop,
                    schema=schema,
                    value=value,
                    dataset=dataset,
                    lang=lang,
                    original_value=original_value,
                    external=False,
                    first_seen=first_seen,
                    last_seen=last_seen,
                )
            )
        entity = self.store.entity_class.from_statements(self.store.dataset, statements)
        entity._caption = obj["c"]
        return entity

    def get_entity(self, id: str) -> Optional[CE]:
        key = f"{self.store.prefix}:e:{id}"
        data = self.store.db.get(key.encode(ENC))
        if data is None:
            return None
        return self._unpack(data)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        key = f"{self.store.prefix}:i:{id}"
        inv_keys = self.store.db.smembers(key.encode(ENC))
        inv_data = self.store.db.mget(inv_keys)
        for data in inv_data:
            if data is None:
                continue
            entity = self._unpack(data)
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
        prefix = f"{self.store.prefix}:e:*"
        batch: List[bytes] = []
        for id in self.store.db.scan_iter(prefix, count=50_000):
            batch.append(id)
            if len(batch) >= 1_000:
                datas = self.store.db.mget(batch)
                for data in datas:
                    if data is None:
                        continue
                    yield self._unpack(data)
                batch = []
        if len(batch):
            datas = self.store.db.mget(batch)
            for data in datas:
                if data is None:
                    continue
                yield self._unpack(data)
