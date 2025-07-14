#
# LevelDB-based store for Nomenklatura.
# A lot of the code in this module is extremely performance-sensitive, so it is unrolled and
# doesn't use helper functions in some places where it would otherwise be more readable.
#
# Specific examples:
# * Not calling a helper to byte-encode values.
# * Not having a helper method for building entities.
import orjson
from pathlib import Path
from typing import Any, Generator, List, Optional, Set, Tuple
from rigour.env import ENCODING as E

import plyvel  # type: ignore
from followthemoney import DS, SE, registry, Property, Statement
from followthemoney.statement.util import get_prop_type

from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer


def unpack_statement(
    keys: List[str],
    data: bytes,
) -> Statement:
    _, canonical_id, ext, dataset, schema, stmt_id = keys
    (
        entity_id,
        prop,
        value,
        lang,
        original_value,
        origin,
        first_seen,
        last_seen,
    ) = orjson.loads(data)
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


class LevelDBStore(Store[DS, SE]):
    def __init__(self, dataset: DS, linker: Linker[SE], path: Path):
        super().__init__(dataset, linker)
        self.path = path
        self.db = plyvel.DB(path.as_posix(), create_if_missing=True)

    def writer(self) -> Writer[DS, SE]:
        return LevelDBWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, SE]:
        return LevelDBView(self, scope, external=external)

    def close(self) -> None:
        self.db.close()


class LevelDBWriter(Writer[DS, SE]):
    BATCH_STATEMENTS = 50_000

    def __init__(self, store: LevelDBStore[DS, SE]):
        self.store: LevelDBStore[DS, SE] = store
        self.batch: Optional[Any] = None
        self.batch_size = 0

    def flush(self) -> None:
        if self.batch is not None:
            self.batch.write()
        self.batch = None
        self.batch_size = 0

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None:
            return
        if self.batch_size >= self.BATCH_STATEMENTS:
            self.flush()
        if self.batch is None:
            self.batch = self.store.db.write_batch()
        canonical_id = self.store.linker.get_canonical(stmt.entity_id)
        stmt.canonical_id = canonical_id

        ext = "x" if stmt.external else ""
        key = f"s:{canonical_id}:{ext}:{stmt.dataset}:{stmt.schema}:{stmt.id}".encode(E)
        values = (
            stmt.entity_id,
            stmt.prop,
            stmt.value,
            stmt.lang or 0,
            stmt.original_value or 0,
            stmt.origin or 0,
            stmt.first_seen,
            stmt.last_seen,
        )
        data = orjson.dumps(values)
        self.batch.put(key, data)
        if get_prop_type(stmt.schema, stmt.prop) == registry.entity.name:
            vc = self.store.linker.get_canonical(stmt.value)
            key = f"i:{vc}:{stmt.canonical_id}".encode(E)
            self.batch.put(key, b"")

        self.batch_size += 1

    def pop(self, entity_id: str) -> List[Statement]:
        if self.batch_size >= self.BATCH_STATEMENTS:
            self.flush()
        if self.batch is None:
            self.batch = self.store.db.write_batch()
        statements: List[Statement] = []
        datasets: Set[str] = set()
        prefix = f"s:{entity_id}:".encode(E)
        with self.store.db.iterator(prefix=prefix) as it:
            for k, v in it:
                self.batch.delete(k)
                stmt = unpack_statement(k.decode(E).split(":"), v)
                statements.append(stmt)
                datasets.add(stmt.dataset)

                if stmt.prop_type == registry.entity.name:
                    vc = self.store.linker.get_canonical(stmt.value)
                    self.batch.delete(f"i:{vc}:{entity_id}".encode(E))
        return list(statements)


class LevelDBView(View[DS, SE]):
    def __init__(
        self, store: LevelDBStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: LevelDBStore[DS, SE] = store
        self.dataset_names: Set[str] = set(scope.dataset_names)

    def has_entity(self, id: str) -> bool:
        prefix = f"s:{id}:".encode(E)
        with self.store.db.iterator(prefix=prefix, include_value=False) as it:
            for v in it:
                _, _, ext, dataset, _, _ = v.decode(E).split(":")
                if dataset not in self.dataset_names:
                    continue
                if ext == "x" and not self.external:
                    continue
                return True
        return False

    def get_entity(self, id: str) -> Optional[SE]:
        statements: List[Statement] = []
        prefix = f"s:{id}:".encode(E)
        with self.store.db.iterator(prefix=prefix) as it:
            for k, v in it:
                keys = k.decode(E).split(":")
                _, _, ext, dataset, _, _ = keys
                if dataset not in self.dataset_names:
                    continue
                if ext == "x" and not self.external:
                    continue
                statements.append(unpack_statement(keys, v))
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        prefix = f"i:{id}:".encode(E)
        with self.store.db.iterator(prefix=prefix, include_value=False) as it:
            for k in it:
                _, _, ref = k.decode(E).split(":")
                entity = self.get_entity(ref)
                if entity is None:
                    continue
                for prop, value in entity.itervalues():
                    if value == id and prop.reverse is not None:
                        yield prop.reverse, entity

    def entities(self) -> Generator[SE, None, None]:
        with self.store.db.iterator(prefix=b"s:", fill_cache=False) as it:
            current_id: Optional[str] = None
            statements: List[Statement] = []
            for k, v in it:
                keys = k.decode(E).split(":")
                _, canonical_id, ext, dataset, schema, _ = keys
                if ext == "x" and not self.external:
                    continue
                if dataset not in self.dataset_names:
                    continue
                # canonical_id = self.store.linker.get_canonical(canonical_id)
                if canonical_id != current_id:
                    if len(statements) > 0:
                        entity = self.store.assemble(statements)
                        if entity is not None:
                            yield entity
                    current_id = canonical_id
                    statements = []
                statements.append(unpack_statement(keys, v))
            if len(statements) > 0:
                entity = self.store.assemble(statements)
                if entity is not None:
                    yield entity
