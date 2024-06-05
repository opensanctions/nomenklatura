import orjson
from pathlib import Path
from typing import Any, Generator, List, Optional, Set, Tuple, Dict

import plyvel  # type: ignore
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.util import pack_prop, unpack_prop


def b(s: str) -> bytes:
    """Encode a string to bytes."""
    return s.encode("utf-8")


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
        1 if stmt.target else 0,
    )
    return orjson.dumps(values)


def unpack_statement(data: bytes, canonical_id: str, external: bool) -> Statement:
    (
        # id,
        entity_id,
        dataset,
        prop_id,
        value,
        lang,
        original_value,
        first_seen,
        # last_seen,
        target,
    ) = orjson.loads(data)
    schema, _, prop = unpack_prop(prop_id)
    return Statement(
        # id=id,
        entity_id=entity_id,
        prop=prop,
        schema=schema,
        value=value,
        lang=None if lang == 0 else lang,
        dataset=dataset,
        original_value=None if original_value == 0 else original_value,
        first_seen=first_seen,
        # last_seen=last_seen,
        target=target == 1,
        canonical_id=canonical_id,
        external=external,
    )


class LevelDBStore(Store[DS, CE]):
    def __init__(self, dataset: DS, linker: Linker[CE], path: Path):
        super().__init__(dataset, linker)
        self.path = path
        self.db = plyvel.DB(path.as_posix(), create_if_missing=True)

    def writer(self) -> Writer[DS, CE]:
        return LevelDBWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return LevelDBView(self, scope, external=external)

    def close(self) -> None:
        self.db.close()


class LevelDBWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 50_000

    def __init__(self, store: LevelDBStore[DS, CE]):
        self.store: LevelDBStore[DS, CE] = store
        self.batch: Optional[Any] = None
        self.last_seens: Dict[str, str] = {}
        self.batch_size = 0

    def flush(self) -> None:
        if self.batch is not None:
            for dataset, last_seen in self.last_seens.items():
                self.batch.put(b(f"ls:{dataset}"), b(last_seen))
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

        key = b(f"e:{canonical_id}:{stmt.dataset}")
        self.batch.put(key, b(stmt.schema))
        if stmt.external:
            key = b(f"x:{canonical_id}:{stmt.id}")
        else:
            key = b(f"s:{canonical_id}:{stmt.id}")
        self.batch.put(key, pack_statement(stmt))
        if stmt.prop_type == registry.entity.name:
            vc = self.store.linker.get_canonical(stmt.value)
            key = b(f"i:{vc}:{stmt.canonical_id}")
            self.batch.put(key, b(stmt.canonical_id))

        self.batch_size += 1

    def pop(self, entity_id: str) -> List[Statement]:
        if self.batch_size >= self.BATCH_STATEMENTS:
            self.flush()
        if self.batch is None:
            self.batch = self.store.db.write_batch()
        statements: List[Statement] = []
        datasets: Set[str] = set()
        for prefix in (f"s:{entity_id}:", f"x:{entity_id}:"):
            with self.store.db.iterator(prefix=b(prefix)) as it:
                for k, v in it:
                    self.batch.delete(k)
                    stmt = unpack_statement(v, entity_id, False)
                    statements.append(stmt)
                    datasets.add(stmt.dataset)

                    if stmt.prop_type == registry.entity.name:
                        vc = self.store.linker.get_canonical(stmt.value)
                        self.batch.delete(b(f"i:{vc}:{entity_id}"))

        for dataset in datasets:
            self.batch.delete(b(f"e:{entity_id}:{dataset}"))

        return list(statements)


class LevelDBView(View[DS, CE]):
    def __init__(
        self, store: LevelDBStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: LevelDBStore[DS, CE] = store
        self.last_seens: Dict[str, str] = {}

    def has_entity(self, id: str) -> bool:
        prefix = b(f"s:{id}:")
        with self.store.db.iterator(
            prefix=prefix, include_key=False, include_value=False
        ) as it:
            for v in it:
                return True
        if self.external:
            prefix = b(f"x:{id}:")
            with self.store.db.iterator(
                prefix=prefix, include_key=False, include_value=False
            ) as it:
                for v in it:
                    return True
        return False

    def get_entity(self, id: str) -> Optional[CE]:
        statements: List[Statement] = []
        prefix = b(f"s:{id}:")
        with self.store.db.iterator(prefix=prefix, include_key=False) as it:
            for v in it:
                statements.append(unpack_statement(v, id, False))
        if self.external:
            prefix = b(f"x:{id}:")
            with self.store.db.iterator(prefix=prefix, include_key=False) as it:
                for v in it:
                    statements.append(unpack_statement(v, id, True))
        for stmt in statements:
            if stmt.dataset not in self.last_seens:
                ls_val = self.store.db.get(b(f"ls:{stmt.dataset}"))
                ls = ls_val.decode("utf-8") if ls_val is not None else None
                self.last_seens[stmt.dataset] = ls
            stmt.last_seen = self.last_seens[stmt.dataset]
        return self.store.assemble(statements)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        prefix = b(f"i:{id}:")
        with self.store.db.iterator(prefix=prefix, include_key=False) as it:
            for v in it:
                entity = self.get_entity(v.decode("utf-8"))
                if entity is None:
                    continue
                for prop, value in entity.itervalues():
                    if value == id and prop.reverse is not None:
                        yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
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
