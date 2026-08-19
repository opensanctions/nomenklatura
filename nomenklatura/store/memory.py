from collections.abc import Generator

from followthemoney import DS, SE, Property, Schema, Statement, registry

from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer


class MemoryStore(Store[DS, SE]):
    """Hold statements in plain dictionaries, with no persistence.

    The right choice for datasets that fit into memory, e.g. when processing
    an entity file on the command line."""

    def __init__(self, dataset: DS, linker: Linker[SE]):
        super().__init__(dataset, linker)
        self.stmts: dict[str, set[Statement]] = {}
        self.inverted: dict[str, set[str]] = {}
        self.entities: dict[str, set[str]] = {}

    def writer(self) -> Writer[DS, SE]:
        return MemoryWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, SE]:
        return MemoryView(self, scope, external=external)


class MemoryWriter(Writer[DS, SE]):
    def __init__(self, store: MemoryStore[DS, SE]):
        self.store: MemoryStore[DS, SE] = store

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

    def pop(self, entity_id: str) -> list[Statement]:
        statements = self.store.stmts.pop(entity_id, set())
        for stmt in statements:
            if stmt.dataset in self.store.entities:
                self.store.entities[stmt.dataset].discard(entity_id)

            if stmt.prop_type == registry.entity.name:
                inverted_id = self.store.linker.get_canonical(stmt.value)
                if inverted_id in self.store.inverted:
                    self.store.inverted[inverted_id].discard(entity_id)

        return list(statements)


class MemoryView(View[DS, SE]):
    def __init__(
        self, store: MemoryStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: MemoryStore[DS, SE] = store

    def has_entity(self, id: str) -> bool:
        for stmt in self.store.stmts.get(id, []):
            if self.external is False and stmt.external:
                continue
            return True
        return False

    def get_entity(self, id: str) -> SE | None:
        if id not in self.store.stmts:
            return None
        stmts: list[Statement] = []
        for stmt in self.store.stmts[id]:
            if self.external is False and stmt.external:
                continue
            stmts.append(stmt)
        return self.store.assemble(stmts)

    def get_inverted(self, id: str) -> Generator[tuple[Property, SE], None, None]:
        for inverted_id in self.store.inverted.get(id, []):
            entity = self.get_entity(inverted_id)
            if entity is None:
                continue
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(
        self, include_schemata: list[Schema] | None = None
    ) -> Generator[SE, None, None]:
        entity_ids: set[str] = set()
        for scope in self.dataset_names:
            entity_ids.update(self.store.entities.get(scope, []))
        for entity_id in entity_ids:
            entity = self.get_entity(entity_id)
            if entity is not None:
                if (
                    include_schemata is not None
                    and entity.schema not in include_schemata
                ):
                    continue
                yield entity
