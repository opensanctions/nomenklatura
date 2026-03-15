#
# KV-based store using bahamut's composite key patterns over Redis/KVRocks.
#
# Key design:
#   d:{dataset}:{version}:s:{entity_id}:{ext}:{stmt_id}:{schema}:{property} → packed value
#   d:{dataset}:{version}:i:{target_entity_id}:{source_entity_id}            → b""
#   d:{dataset}:{version}:e:{entity_id}                                      → schema name
#   meta:versions:{dataset}:{version}                                        → release timestamp
#   meta:latest:{dataset}                                                    → version string
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

from redis.client import Redis
from followthemoney import DS, SE, Schema, registry, Property, Statement
from followthemoney.statement.util import get_prop_type

from nomenklatura.kv import get_redis, close_redis
from nomenklatura.versions import Version
from nomenklatura.resolver import Linker, StrIdent
from nomenklatura.store.base import Store, View, Writer

log = logging.getLogger(__name__)
MGET_BATCH = 500


def _unpack_statement(
    parts: List[str],
    data: bytes,
    canonical_id: str,
) -> Statement:
    # parts: d, dataset, version, s, entity_id, ext, stmt_id, schema, property
    entity_id = parts[4]
    ext = parts[5]
    stmt_id = parts[6]
    schema = parts[7]
    prop = parts[8]
    value, lang, original_value, origin, first_seen, last_seen = orjson.loads(data)
    return Statement(
        id=stmt_id,
        entity_id=entity_id,
        prop=prop,
        schema=schema,
        value=value,
        lang=None if lang == 0 else lang,
        dataset=parts[1],
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
        # Check if any data keys exist for this dataset+version
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
        self._pipeline = self.store.db.pipeline()
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
        key = f"d:{self.ds_ver}:s:{entity_id}:{ext}:{stmt.id}:{stmt.schema}:{stmt.prop}".encode(
            E
        )
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
        self._pipeline.set(key, value)

        # Entity marker
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

    def _prefix_scan(self, prefix: bytes) -> Generator[Tuple[bytes, bytes], None, None]:
        # Batch keys and use MGET to avoid N individual GET round-trips.
        batch: List[bytes] = []
        for key in self.store.db.scan_iter(match=prefix + b"*"):
            batch.append(key)
            if len(batch) >= MGET_BATCH:
                values = self.store.db.mget(batch)
                for k, v in zip(batch, values):
                    if v is not None:
                        yield k, v
                batch = []
        if batch:
            values = self.store.db.mget(batch)
            for k, v in zip(batch, values):
                if v is not None:
                    yield k, v

    def has_entity(self, id: str) -> bool:
        for sid in self.store.linker.connected_plain(id):
            for ds, ver in self.vers:
                prefix = f"d:{ds}:{ver}:s:{sid}:".encode(E)
                for key in self.store.db.scan_iter(match=prefix + b"*", count=1):
                    if not self.external:
                        parts = key.decode(E).split(":")
                        if parts[5] == "x":
                            continue
                    return True
        return False

    def get_entity(self, id: str) -> Optional[SE]:
        statements: List[Statement] = []
        canonical_id = self.store.linker.get_canonical(id)
        for sid in self.store.linker.connected_plain(id):
            for ds, ver in self.vers:
                prefix = f"d:{ds}:{ver}:s:{sid}:".encode(E)
                for key, value in self._prefix_scan(prefix):
                    parts = key.decode(E).split(":")
                    ext = parts[5]
                    if ext == "x" and not self.external:
                        continue
                    statements.append(_unpack_statement(parts, value, canonical_id))
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
        for ds, ver in self.vers:
            prefix = f"d:{ds}:{ver}:s:{entity_id}:".encode(E)
            for key, value in self._prefix_scan(prefix):
                parts = key.decode(E).split(":")
                stmt_id = parts[6]
                vals = orjson.loads(value)
                first_seen = vals[4]
                if first_seen:
                    timestamps[stmt_id] = first_seen
        return timestamps

    def entities(
        self, include_schemata: Optional[List[Schema]] = None
    ) -> Generator[SE, None, None]:
        seen: Set[str] = set()
        schema_names: Optional[Set[bytes]] = None
        if include_schemata is not None:
            schema_names = {s.name.encode(E) for s in include_schemata if s is not None}

        for ds, ver in self.vers:
            marker_prefix = f"d:{ds}:{ver}:e:".encode(E)
            for key, schema_bytes in self._prefix_scan(marker_prefix):
                entity_id = key.decode(E).split(":")[4]

                # Schema pre-filter before hitting statements
                if schema_names is not None:
                    if schema_bytes not in schema_names:
                        continue

                # Canonicalize
                canonical_id = self.store.linker.get_canonical(entity_id)

                # Dedup merged entities
                if canonical_id in seen:
                    continue
                if canonical_id != entity_id:
                    seen.add(canonical_id)

                entity = self.get_entity(canonical_id)
                if entity is not None:
                    if schema_names is not None:
                        if entity.schema.name.encode(E) not in schema_names:
                            continue
                    yield entity
