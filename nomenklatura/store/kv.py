#
# KV-based store using Redis Hashes over Redis/KVRocks.
#
# Key design:
#   d:{dataset}:{version}:s:{entity_id}  → Hash { "{ext}:{stmt_id}:{schema}:{prop}" → packed value }
#   d:{dataset}:{version}:i:{target_entity_id}:{source_entity_id} → b""
#   d:{dataset}:{version}:e:{entity_id}  → schema name
#   meta:versions:{dataset}:{version}    → release timestamp
#
# Each entity's statements are stored as fields in a single Redis Hash keyed by
# entity_id. This allows HGETALL to retrieve all statements for an entity in one
# round-trip, and pipelined HGETALL to batch entity fetches.
#
# Statements are stored under raw source entity IDs (not canonical). The linker
# resolves canonical IDs at read time (late-binding canonicalization).
#
# A lot of the code in this module is performance-sensitive, so it is unrolled and
# doesn't use helper functions in some places where it would otherwise be more readable.
#
import time
import orjson
import logging
from typing import Dict, Generator, List, Optional, Set, Tuple
from rigour.env import ENCODING as E

from redis.client import Redis, Pipeline
from followthemoney import DS, SE, Schema, registry, Property, Statement
from followthemoney.statement.util import get_prop_type

from nomenklatura.kv import get_redis, close_redis
from nomenklatura.versions import Version
from nomenklatura.resolver import Linker, StrIdent
from nomenklatura.store.base import Store, View, Writer

log = logging.getLogger(__name__)
HGETALL_BATCH = 200
MARKER_BATCH = 500


def _unpack_hash_statement(
    dataset: str,
    entity_id: str,
    field: bytes,
    data: bytes,
    canonical_id: str,
) -> Statement:
    # field: {ext}:{stmt_id}:{schema}:{prop}
    parts = field.decode(E).split(":")
    ext = parts[0]
    stmt_id = parts[1]
    schema = parts[2]
    prop = parts[3]
    value, lang, original_value, origin, first_seen, last_seen = orjson.loads(data)
    return Statement(
        id=stmt_id,
        entity_id=entity_id,
        prop=prop,
        schema=schema,
        value=value,
        lang=None if lang == 0 else lang,
        dataset=dataset,
        original_value=None if original_value == 0 else original_value,
        origin=None if origin == 0 else origin,
        first_seen=first_seen,
        last_seen=last_seen,
        canonical_id=canonical_id,
        external=ext == "x",
    )


class KVStore(Store[DS, SE]):
    def __init__(
        self,
        dataset: DS,
        linker: Linker[SE],
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
    ) -> "KVWriter[DS, SE]":
        if version is None:
            version = Version.new().id
        dataset = dataset or self.dataset
        return KVWriter(self, dataset=dataset, version=version)

    def view(
        self,
        scope: DS,
        external: bool = False,
        versions: Optional[Dict[str, str]] = None,
    ) -> "KVView[DS, SE]":
        return KVView(self, scope, external=external, versions=versions)

    def update(self, id: StrIdent) -> None:
        # Noop — late-binding canonicalization makes this unnecessary.
        return

    def get_latest(self, dataset: str) -> Optional[str]:
        history = self.get_history(dataset)
        return history[0] if history else None

    def get_history(self, dataset: str) -> List[str]:
        prefix = f"meta:versions:{dataset}:".encode(E)
        versions: List[str] = []
        for key in self.db.scan_iter(match=prefix + b"*"):
            version = key.decode(E).rsplit(":", 1)[-1]
            versions.append(version)
        return sorted(versions, reverse=True)

    def has_version(self, dataset: str, version: str) -> bool:
        prefix = f"d:{dataset}:{version}:e:".encode(E)
        for _ in self.db.scan_iter(match=prefix + b"*", count=1):
            return True
        return False

    def release_version(self, dataset: str, version: str) -> None:
        self.db.set(
            f"meta:versions:{dataset}:{version}".encode(E),
            str(time.time()).encode(E),
        )
        log.info("Released store version: %s (%s)", dataset, version)

    def drop_version(self, dataset: str, version: str) -> None:
        prefix = f"d:{dataset}:{version}:".encode(E)
        pipeline = self.db.pipeline()
        cmds = 0
        for key in self.db.scan_iter(match=prefix + b"*"):
            pipeline.delete(key)
            cmds += 1
            if cmds >= 1_000:
                pipeline.execute()
                pipeline = self.db.pipeline()
                cmds = 0
        if cmds > 0:
            pipeline.execute()

        self.db.delete(f"meta:versions:{dataset}:{version}".encode(E))
        log.info("Dropped store version: %s (%s)", dataset, version)

    def close(self) -> None:
        close_redis()


class KVWriter(Writer[DS, SE]):
    BATCH_STATEMENTS = 50_000

    def __init__(
        self,
        store: KVStore[DS, SE],
        dataset: DS,
        version: str,
    ):
        self.store: KVStore[DS, SE] = store
        self.dataset = dataset
        self.version = version
        self.ds_ver = f"{dataset.name}:{version}"
        self._pipeline: Pipeline = self.store.db.pipeline()
        self._batch_size = 0

    def flush(self) -> None:
        if self._batch_size > 0:
            self._pipeline.execute()
            self._pipeline = self.store.db.pipeline()
            self._batch_size = 0

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None or stmt.id is None:
            return
        if self._batch_size >= self.BATCH_STATEMENTS:
            self.flush()

        entity_id = stmt.entity_id
        ext = "x" if stmt.external else ""

        # Statement as hash field
        hash_key = f"d:{self.ds_ver}:s:{entity_id}".encode(E)
        field = f"{ext}:{stmt.id}:{stmt.schema}:{stmt.prop}".encode(E)
        value = orjson.dumps(
            (
                stmt.value,
                stmt.lang or 0,
                stmt.original_value or 0,
                stmt.origin or 0,
                stmt.first_seen,
                stmt.last_seen,
            )
        )
        self._pipeline.hset(hash_key, field, value)

        # Entity marker (for schema pre-filtering and discovery)
        self._pipeline.set(
            f"d:{self.ds_ver}:e:{entity_id}".encode(E),
            stmt.schema.encode(E),
        )

        # Inverted index for entity-typed properties
        if get_prop_type(stmt.schema, stmt.prop) == registry.entity.name:
            self._pipeline.set(
                f"d:{self.ds_ver}:i:{stmt.value}:{entity_id}".encode(E),
                b"",
            )

        self._batch_size += 1

    def pop(self, entity_id: str) -> List[Statement]:
        raise NotImplementedError()

    def close(self) -> None:
        self.flush()


class KVView(View[DS, SE]):
    def __init__(
        self,
        store: KVStore[DS, SE],
        scope: DS,
        external: bool = False,
        versions: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: KVStore[DS, SE] = store

        self.vers: List[Tuple[str, str]] = []
        if versions is None:
            versions = {}
        for ds in scope.leaf_names:
            version = versions.get(ds, self.store.get_latest(ds))
            if version is not None:
                self.vers.append((ds, version))

    def _hgetall_entity(
        self,
        source_ids: List[str],
        canonical_id: str,
    ) -> List[Statement]:
        """Fetch all statements for a set of source IDs using pipelined HGETALL."""
        pipe = self.store.db.pipeline()
        lookups: List[Tuple[str, str]] = []  # (dataset, entity_id)
        for sid in source_ids:
            for ds, ver in self.vers:
                pipe.hgetall(f"d:{ds}:{ver}:s:{sid}".encode(E))
                lookups.append((ds, sid))
        results = pipe.execute()
        statements: List[Statement] = []
        for (ds, sid), fields in zip(lookups, results):
            if not fields:
                continue
            for field, data in fields.items():
                ext = field[0:1]  # b"x" or b""[0:1]
                if ext == b"x" and not self.external:
                    continue
                statements.append(
                    _unpack_hash_statement(ds, sid, field, data, canonical_id)
                )
        return statements

    def has_entity(self, id: str) -> bool:
        if self.external:
            # Any statement counts — just check hash existence.
            pipe = self.store.db.pipeline()
            count = 0
            for sid in self.store.linker.connected_plain(id):
                for ds, ver in self.vers:
                    pipe.exists(f"d:{ds}:{ver}:s:{sid}".encode(E))
                    count += 1
            if count == 0:
                return False
            results = pipe.execute()
            return any(r > 0 for r in results)

        # Non-external view: must check that at least one internal field exists.
        for sid in self.store.linker.connected_plain(id):
            for ds, ver in self.vers:
                fields = self.store.db.hgetall(f"d:{ds}:{ver}:s:{sid}".encode(E))
                for field in fields:
                    if field[0:1] != b"x":
                        return True
        return False

    def get_entity(self, id: str) -> Optional[SE]:
        canonical_id = self.store.linker.get_canonical(id)
        source_ids = list(self.store.linker.connected_plain(id))
        statements = self._hgetall_entity(source_ids, canonical_id)
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        refs: Set[str] = set()
        for sid in self.store.linker.connected_plain(id):
            for ds, ver in self.vers:
                prefix = f"d:{ds}:{ver}:i:{sid}:".encode(E)
                for key in self.store.db.scan_iter(match=prefix + b"*"):
                    ref_entity_id = key.decode(E).rsplit(":", 1)[-1]
                    refs.add(self.store.linker.get_canonical(ref_entity_id))

        for ref_canonical in refs:
            entity = self.get_entity(ref_canonical)
            if entity is None:
                continue
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def get_timestamps(self, entity_id: str) -> Dict[str, str]:
        """Get first_seen timestamps for all statements of a raw entity ID.

        Returns a dict mapping statement IDs to their first_seen timestamps.
        Operates on raw entity IDs (not canonical) — the caller knows the
        source entity ID from the statement being written.
        """
        timestamps: Dict[str, str] = {}
        pipe = self.store.db.pipeline()
        ds_list: List[str] = []
        for ds, ver in self.vers:
            pipe.hgetall(f"d:{ds}:{ver}:s:{entity_id}".encode(E))
            ds_list.append(ds)
        results = pipe.execute()
        for ds, fields in zip(ds_list, results):
            if not fields:
                continue
            for field, data in fields.items():
                parts = field.decode(E).split(":")
                stmt_id = parts[1]
                vals = orjson.loads(data)
                first_seen = vals[4]
                if first_seen:
                    timestamps[stmt_id] = first_seen
        return timestamps

    def entities(
        self, include_schemata: Optional[List[Schema]] = None
    ) -> Generator[SE, None, None]:
        schema_names: Optional[Set[bytes]] = None
        if include_schemata is not None:
            schema_names = {s.name.encode(E) for s in include_schemata if s is not None}

        # Step 1: Discover all entities via markers and group by canonical ID.
        # canonical_id → list of (dataset, source_entity_id) tuples
        canonical_sources: Dict[str, List[Tuple[str, str]]] = {}
        canonical_order: List[str] = []

        for ds, ver in self.vers:
            marker_prefix = f"d:{ds}:{ver}:e:".encode(E)
            batch: List[bytes] = []
            for key in self.store.db.scan_iter(match=marker_prefix + b"*"):
                batch.append(key)
                if len(batch) >= MARKER_BATCH:
                    values = self.store.db.mget(batch)
                    for k, v in zip(batch, values):
                        if v is None:
                            continue
                        if schema_names is not None and v not in schema_names:
                            continue
                        entity_id = k.decode(E).split(":")[4]
                        canonical_id = self.store.linker.get_canonical(entity_id)
                        if canonical_id not in canonical_sources:
                            canonical_sources[canonical_id] = []
                            canonical_order.append(canonical_id)
                        canonical_sources[canonical_id].append((ds, entity_id))
                    batch = []
            if batch:
                values = self.store.db.mget(batch)
                for k, v in zip(batch, values):
                    if v is None:
                        continue
                    if schema_names is not None and v not in schema_names:
                        continue
                    entity_id = k.decode(E).split(":")[4]
                    canonical_id = self.store.linker.get_canonical(entity_id)
                    if canonical_id not in canonical_sources:
                        canonical_sources[canonical_id] = []
                        canonical_order.append(canonical_id)
                    canonical_sources[canonical_id].append((ds, entity_id))

        # Step 2: Batch HGETALL in pipeline chunks, assemble and yield entities.
        for batch_start in range(0, len(canonical_order), HGETALL_BATCH):
            batch_ids = canonical_order[batch_start : batch_start + HGETALL_BATCH]
            pipe = self.store.db.pipeline()
            # (canonical_id, dataset, source_entity_id) per pipeline command
            lookups: List[Tuple[str, str, str]] = []
            for cid in batch_ids:
                for ds, sid in canonical_sources[cid]:
                    for d, ver in self.vers:
                        if d == ds:
                            pipe.hgetall(f"d:{ds}:{ver}:s:{sid}".encode(E))
                            lookups.append((cid, ds, sid))
                            break

            results = pipe.execute()

            # Group statements by canonical
            by_canonical: Dict[str, List[Statement]] = {}
            for (cid, ds, sid), fields in zip(lookups, results):
                if not fields:
                    continue
                for field, data in fields.items():
                    ext = field[0:1]
                    if ext == b"x" and not self.external:
                        continue
                    stmt = _unpack_hash_statement(ds, sid, field, data, cid)
                    if cid not in by_canonical:
                        by_canonical[cid] = []
                    by_canonical[cid].append(stmt)

            for cid in batch_ids:
                stmts = by_canonical.get(cid)
                if stmts is None:
                    continue
                entity = self.store.assemble(stmts)
                if entity is not None:
                    if schema_names is not None:
                        if entity.schema.name.encode(E) not in schema_names:
                            continue
                    yield entity
