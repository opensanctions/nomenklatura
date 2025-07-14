import orjson
from pathlib import Path
from typing import Any, Generator, List, Optional, Set, Tuple, Dict
from rigour.env import ENCODING as E

import plyvel  # type: ignore
from followthemoney import DS, SE, registry, Property, Statement
from followthemoney.statement.util import pack_prop, unpack_prop

from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer


def pack_statement(stmt: Statement) -> bytes:
    values = (
        # stmt.id,
        stmt.entity_id,
        stmt.dataset,
        pack_prop(stmt.schema, stmt.prop),
        stmt.value,
        stmt.lang or 0,
        stmt.original_value or 0,
        stmt.first_seen,
        # stmt.last_seen,
    )
    return orjson.dumps(values)


def unpack_statement(
    data: bytes, canonical_id: str, id: str, external: bool
) -> Statement:
    (
        entity_id,
        dataset,
        prop_id,
        value,
        lang,
        original_value,
        first_seen,
        # last_seen,
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
        # last_seen=last_seen,
        canonical_id=canonical_id,
        external=external,
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
        self.last_seens: Dict[str, str] = {}
        self.batch_size = 0

    def flush(self) -> None:
        if self.batch is not None:
            for dataset, last_seen in self.last_seens.items():
                bkey = f"ls:{dataset}".encode(E)
                self.batch.put(bkey, last_seen.encode(E))
            self.batch.write()
        self.last_seens = {}
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

        if stmt.last_seen is not None:
            self.last_seens[stmt.dataset] = stmt.last_seen

        key = f"e:{canonical_id}:{stmt.dataset}".encode(E)
        self.batch.put(key, stmt.schema.encode(E))
        if stmt.external:
            key = f"x:{canonical_id}:{stmt.id}".encode(E)
        else:
            key = f"s:{canonical_id}:{stmt.id}".encode(E)
        self.batch.put(key, pack_statement(stmt))
        if stmt.prop_type == registry.entity.name:
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
        for prefix in (f"s:{entity_id}:", f"x:{entity_id}:"):
            with self.store.db.iterator(prefix=prefix.encode(E)) as it:
                for k, v in it:
                    self.batch.delete(k)
                    stmt = unpack_statement(v, entity_id, False)
                    statements.append(stmt)
                    datasets.add(stmt.dataset)

                    if stmt.prop_type == registry.entity.name:
                        vc = self.store.linker.get_canonical(stmt.value)
                        self.batch.delete(f"i:{vc}:{entity_id}".encode(E))

        for dataset in datasets:
            self.batch.delete(f"e:{entity_id}:{dataset}".encode(E))

        return list(statements)


class LevelDBView(View[DS, SE]):
    def __init__(
        self, store: LevelDBStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: LevelDBStore[DS, SE] = store
        self.last_seens: Dict[str, Optional[str]] = {}
        for dataset in scope.datasets:
            if dataset.is_collection:
                continue
            ls_val = self.store.db.get(f"ls:{dataset.name}".encode(E))
            ls = ls_val.decode("utf-8") if ls_val is not None else None
            self.last_seens[dataset.name] = ls

    def has_entity(self, id: str) -> bool:
        prefix = f"s:{id}:".encode(E)
        with self.store.db.iterator(
            prefix=prefix, include_key=False, include_value=False
        ) as it:
            for v in it:
                return True
        if self.external:
            prefix = f"x:{id}:".encode(E)
            with self.store.db.iterator(
                prefix=prefix, include_key=False, include_value=False
            ) as it:
                for v in it:
                    return True
        return False

    def get_entity(self, id: str) -> Optional[SE]:
        statements: List[Statement] = []
        prefix = f"s:{id}:".encode(E)
        with self.store.db.iterator(prefix=prefix, include_key=True) as it:
            for k, v in it:
                _, _, stmt_id = k.decode("utf-8").split(":")
                statements.append(unpack_statement(v, id, stmt_id, False))
        if self.external:
            prefix = f"x:{id}:".encode(E)
            with self.store.db.iterator(prefix=prefix, include_key=True) as it:
                for k, v in it:
                    _, _, stmt_id = k.decode("utf-8").split(":")
                    statements.append(unpack_statement(v, id, stmt_id, False))
        for stmt in statements:
            stmt.last_seen = self.last_seens[stmt.dataset]
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        prefix = f"i:{id}:".encode(E)
        with self.store.db.iterator(
            prefix=prefix, include_key=True, include_value=False
        ) as it:
            for k in it:
                _, _, ref = k.decode("utf-8").split(":")
                entity = self.get_entity(ref)
                if entity is None:
                    continue
                for prop, value in entity.itervalues():
                    if value == id and prop.reverse is not None:
                        yield prop.reverse, entity

    def entities(self) -> Generator[SE, None, None]:
        prefix = b"e:"
        with self.store.db.iterator(prefix=prefix, include_value=False) as it:
            current_id: Optional[str] = None
            current_match = False
            for k in it:
                _, entity_id, dataset = k.decode("utf-8").split(":", 2)
                if entity_id != current_id:
                    current_id = entity_id
                    current_match = False
                if current_match:
                    continue
                if dataset in self.dataset_names:
                    current_match = True
                    entity = self.get_entity(entity_id)
                    if entity is not None:
                        yield entity
