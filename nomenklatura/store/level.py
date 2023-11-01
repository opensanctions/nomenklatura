from pathlib import Path
from typing import Any, Generator, List, Optional, Set, Tuple

import plyvel  # type: ignore
from followthemoney.property import Property
from followthemoney.types import registry

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Resolver
from nomenklatura.statement import Statement
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.store.util import b, pack_statement, unpack_statement


class LevelDBStore(Store[DS, CE]):
    def __init__(self, dataset: DS, resolver: Resolver[CE], path: Path):
        super().__init__(dataset, resolver)
        self.path = path
        self.db = plyvel.DB(path.as_posix(), create_if_missing=True)

    def writer(self) -> Writer[DS, CE]:
        return LevelDBWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return LevelDBView(self, scope, external=external)

    def close(self) -> None:
        self.db.close()


class LevelDBWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 50000

    def __init__(self, store: LevelDBStore[DS, CE]):
        self.store: LevelDBStore[DS, CE] = store
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
        canonical_id = self.store.resolver.get_canonical(stmt.entity_id)
        stmt.canonical_id = canonical_id

        key = b(f"e:{canonical_id}:{stmt.dataset}")
        self.batch.put(key, b(stmt.schema))
        if stmt.external:
            key = b(f"x:{canonical_id}:{stmt.id}")
        else:
            key = b(f"s:{canonical_id}:{stmt.id}")
        self.batch.put(key, pack_statement(stmt))
        if stmt.prop_type == registry.entity.name:
            vc = self.store.resolver.get_canonical(stmt.value)
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
                        vc = self.store.resolver.get_canonical(stmt.value)
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
