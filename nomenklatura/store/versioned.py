import orjson
import logging
from redis.client import Redis
from typing import Generator, List, Optional, Set, Tuple, Dict
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.kv import b, bv, get_redis, close_redis
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.versions import Version
from nomenklatura.resolver import Linker, Identifier, StrIdent
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.util import pack_prop, unpack_prop

log = logging.getLogger(__name__)


def _pack_statement(stmt: Statement) -> bytes:
    values = (
        stmt.id,
        stmt.entity_id,
        stmt.dataset,
        pack_prop(stmt.schema, stmt.prop),
        stmt.value,
        stmt.lang or 0,
        stmt.original_value or 0,
        stmt.first_seen,
        stmt.last_seen,
        1 if stmt.target else 0,
        1 if stmt.external else 0,
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
        lang=None if lang == 0 else lang,
        dataset=dataset,
        original_value=None if original_value == 0 else original_value,
        first_seen=first_seen,
        last_seen=last_seen,
        target=target == 1,
        canonical_id=canonical_id or entity_id,
        external=external == 1,
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

    def writer(
        self,
        dataset: Optional[DS] = None,
        version: Optional[str] = None,
        timestamps: bool = False,
    ) -> "VersionedRedisWriter[DS, CE]":
        if version is None:
            version = Version.new().id
        dataset = dataset or self.dataset
        return VersionedRedisWriter(
            self,
            dataset=dataset,
            version=version,
            timestamps=timestamps,
        )

    def view(
        self, scope: DS, external: bool = False, versions: Dict[str, str] = {}
    ) -> "VersionedRedisView[DS, CE]":
        return VersionedRedisView(self, scope, external=external, versions=versions)

    def update(self, id: StrIdent) -> None:
        # Noop because the VersionedStore is not resolved.
        return

    def get_latest(self, dataset: str) -> Optional[str]:
        """Get the latest version of a dataset in the store."""
        val = self.db.get(b(f"ds:{dataset}:latest"))
        return val.decode("utf-8") if val is not None else None

    def get_history(self, dataset: str) -> List[str]:
        """List all versions of a dataset present in the store."""
        values = self.db.lrange(f"ds:{dataset}:history", 0, -1)
        return [v.decode("utf-8") for v in values]

    def has_version(self, dataset: str, version: str) -> bool:
        """Check if a specific version of a dataset exists in the store."""
        return self.db.exists(f"ents:{dataset}:{version}") > 0

    def release_version(self, dataset: str, version: str) -> None:
        """Release the given version of the dataset (i.e. tag it as the latest
        version in the relevant lookup key)."""
        history_key = b(f"ds:{dataset}:history")
        idx = self.db.lpos(history_key, b(version))
        if idx is None:
            self.db.lpush(history_key, b(version))
        latest = self.db.lindex(history_key, 0)
        if latest is not None:
            self.db.set(b(f"ds:{dataset}:latest"), latest)
        log.info("Released store version: %s (%s)", dataset, version)

    def drop_version(self, dataset: str, version: str) -> None:
        """Delete all data associated with a specific version of a dataset."""
        pipeline = self.db.pipeline()
        cmds = 0
        for prefix in ["stmt", "ents", "inv"]:
            query = f"{prefix}:{dataset}:{version}*"
            for key in self.db.scan_iter(query):
                pipeline.delete(key)
                cmds += 1
                if cmds > 1_000:
                    pipeline.execute()
                    pipeline = self.db.pipeline()
                    cmds = 0
        if cmds > 0:
            pipeline.execute()

        # TODO: do we even want to remove the version from the history list?
        self.db.lrem(f"ds:{dataset}:history", 0, b(version))
        latest_key = f"ds:{dataset}:latest"
        if b(version) == self.db.get(latest_key):
            previous = self.db.lindex(b(f"ds:{dataset}:history"), 0)
            if previous is not None:
                self.db.set(latest_key, previous)
            else:
                self.db.delete(latest_key)
        log.info("Dropped store version: %s (%s)", dataset, version)

    def close(self) -> None:
        close_redis()


class VersionedRedisWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 2_000

    def __init__(
        self,
        store: VersionedRedisStore[DS, CE],
        dataset: DS,
        version: str,
        timestamps: bool = False,
    ):
        self.version = version
        self.dataset = dataset
        self.timestamps = timestamps
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

        if len(statements) == 0:
            return

        # Merge with previous version to get accurate first_seen timestamps
        if self.timestamps and self.prev:
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
        self.store.release_version(self.dataset.name, self.version)

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
        self,
        store: VersionedRedisStore[DS, CE],
        scope: DS,
        external: bool = False,
        versions: Dict[str, str] = {},
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: VersionedRedisStore[DS, CE] = store

        # Get the latest version for each dataset in the scope
        self.vers: List[Tuple[str, str]] = []
        for ds in scope.leaf_names:
            version = versions.get(ds, self.store.get_latest(ds))
            if version is not None:
                self.vers.append((ds, version))

    def _get_stmt_keys(self, entity_id: str) -> List[str]:
        keys: List[str] = []
        ident = Identifier.get(entity_id)
        for id in self.store.linker.connected(ident):
            keys.extend([f"stmt:{d}:{v}:{id}" for d, v in self.vers])
        return keys

    def has_entity(self, id: str) -> bool:
        # FIXME: this implementation does not account for the `external` flag
        # correctly because it does not check the `stmt.external` field for
        # each statement.
        return self.store.db.exists(*self._get_stmt_keys(id)) > 0

    def _get_statements(self, id: str) -> Generator[Statement, None, None]:
        keys = self._get_stmt_keys(id)
        if len(keys) == 0:
            return None
        elif len(keys) == 1:
            stmts = self.store.db.smembers(keys[0])
        else:
            stmts = {bv(s) for s in self.store.db.sunion(keys)}
        for v in stmts:
            stmt = _unpack_statement(bv(v), id)
            yield stmt

    def get_timestamps(self, id: str) -> Dict[str, str]:
        """Get the first seen timestamps associated with all statements of an entity.

        Returns a dictionary mapping statement IDs to their first seen timestamps.
        This can be used by an ETL to generate continuous entity histories.
        """
        timestamps: Dict[str, str] = {}
        for stmt in self._get_statements(id):
            if stmt.id is not None and stmt.first_seen is not None:
                timestamps[stmt.id] = stmt.first_seen
        return timestamps

    def get_entity(self, id: str) -> Optional[CE]:
        statements: List[Statement] = []
        for stmt in self._get_statements(id):
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
        refs = (
            {bv(v) for v in self.store.db.sunion(keys)}
            if len(keys) > 0
            else self.store.db.smembers(keys[0])
        )
        entities: Set[str] = set()
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

    def statements(self, resolve: bool = False) -> Generator[Statement, None, None]:
        """Iterate over all statements in the view. If `resolve` is set to `True`,
        canonical IDs are applied to the statement and its value.

        NOTE: The `external` flag of the view will be used to filter statements, too.
        """
        for ds, ver in self.vers:
            for id in self.store.db.sscan_iter(b(f"ents:{ds}:{ver}")):
                entity_id = id.decode("utf-8")
                stmt_key = f"stmt:{ds}:{ver}:{entity_id}"
                for stmt_text in self.store.db.smembers(b(stmt_key)):
                    stmt = _unpack_statement(stmt_text, entity_id)
                    if stmt.external and not self.external:
                        continue
                    if resolve:
                        stmt = self.store.linker.apply_statement(stmt)
                    yield stmt

    def entities(self) -> Generator[CE, None, None]:
        if len(self.vers) == 0:
            return
        if len(self.vers) == 1:
            scope_name = b(f"ents:{self.vers[0][0]}:{self.vers[0][1]}")
        if len(self.vers) > 1:
            version = Version.new().id + ":iter"
            scope_name = b(f"ents:{self.scope.name}:{version}")
            parts = [b(f"ents:{d}:{v}") for d, v in self.vers]
            self.store.db.sunionstore(scope_name, parts)

        # Keep track of canonical entities to avoid yielding the same
        # de-duplicated entity multiple times. This intrinsically leaks
        # memory, so we're being careful to only record entity IDs
        # that are part of a cluster with more than one ID.
        try:
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
        finally:
            if len(self.vers) > 1:
                self.store.db.delete(scope_name)
