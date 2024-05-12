from typing import Dict, Set, List, Optional, Generator, Tuple
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.store.base import Store, View, Writer
from nomenklatura.statement import Statement
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Linker


class MemoryStore(Store[DS, CE]):
    def __init__(self, dataset: DS, linker: Linker[CE]):
        super().__init__(dataset, linker)
        self.stmts: Dict[str, Set[Statement]] = {}
        self.inverted: Dict[str, Set[str]] = {}
        self.entities: Dict[str, Set[str]] = {}

    def writer(self) -> Writer[DS, CE]:
        return MemoryWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return MemoryView(self, scope, external=external)


class MemoryWriter(Writer[DS, CE]):
    def __init__(self, store: MemoryStore[DS, CE]):
        self.store: MemoryStore[DS, CE] = store

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None:
            return
        canonical_id = stmt.canonical_id or self.store.linker.get_canonical(
            stmt.entity_id
        )
        if canonical_id not in self.store.stmts:
            self.store.stmts[canonical_id] = set()
        self.store.stmts[canonical_id].add(stmt)

        if stmt.dataset not in self.store.entities:
            self.store.entities[stmt.dataset] = set()
        self.store.entities[stmt.dataset].add(canonical_id)

        if stmt.prop_type == registry.entity.name:
            inverted_id = self.store.linker.get_canonical(stmt.value)
            if inverted_id not in self.store.inverted:
                self.store.inverted[inverted_id] = set()
            self.store.inverted[inverted_id].add(canonical_id)

    def pop(self, entity_id: str) -> List[Statement]:
        statements = self.store.stmts.pop(entity_id, set())
        for stmt in statements:
            if stmt.dataset in self.store.entities:
                self.store.entities[stmt.dataset].discard(entity_id)

            if stmt.prop_type == registry.entity.name:
                inverted_id = self.store.linker.get_canonical(stmt.value)
                if inverted_id in self.store.inverted:
                    self.store.inverted[inverted_id].discard(entity_id)

        return list(statements)


class MemoryView(View[DS, CE]):
    def __init__(
        self, store: MemoryStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: MemoryStore[DS, CE] = store

    def has_entity(self, id: str) -> bool:
        for stmt in self.store.stmts.get(id, []):
            if self.external is False and stmt.external:
                continue
            return True
        return False

    def get_entity(self, id: str) -> Optional[CE]:
        if id not in self.store.stmts:
            return None
        stmts: List[Statement] = []
        for stmt in self.store.stmts[id]:
            if self.external is False and stmt.external:
                continue
            stmts.append(stmt)
        return self.store.assemble(stmts)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        for inverted_id in self.store.inverted.get(id, []):
            entity = self.get_entity(inverted_id)
            if entity is None:
                continue
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
        entity_ids: Set[str] = set()
        for scope in self.dataset_names:
            entity_ids.update(self.store.entities.get(scope, []))
        for entity_id in entity_ids:
            entity = self.get_entity(entity_id)
            if entity is not None:
                yield entity
