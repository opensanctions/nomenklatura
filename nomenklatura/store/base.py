from types import TracebackType
from typing import Optional, Generator, List, Tuple, Generic, Type, cast
from followthemoney import Schema, registry, Property, DS, Statement
from followthemoney import StatementEntity, SE
from followthemoney.statement.util import get_prop_type

from nomenklatura.resolver import Linker, StrIdent


class Store(Generic[DS, SE]):
    """A data storage and retrieval mechanism for statement-based entity data.
    Essentially, this is a triple store which can be implemented using various
    backends."""

    def __init__(self, dataset: DS, linker: Linker[SE]):
        self.dataset = dataset
        self.linker = linker
        self.entity_class = cast(Type[SE], StatementEntity)

    def writer(self) -> "Writer[DS, SE]":
        raise NotImplementedError()

    def view(self, scope: DS, external: bool = False) -> "View[DS, SE]":
        raise NotImplementedError()

    def default_view(self, external: bool = False) -> "View[DS, SE]":
        return self.view(self.dataset, external=external)

    def assemble(self, statements: List[Statement]) -> Optional[SE]:
        if not len(statements):
            return None
        for stmt in statements:
            if get_prop_type(stmt.schema, stmt.prop) == registry.entity.name:
                stmt.value = self.linker.get_canonical(stmt.value)
        entity = self.entity_class.from_statements(self.dataset, statements)
        if entity.id is not None:
            entity.extra_referents.update(self.linker.get_referents(entity.id))
        return entity

    def update(self, id: StrIdent) -> None:
        canonical_id = self.linker.get_canonical(id)
        with self.writer() as writer:
            for referent in self.linker.get_referents(canonical_id):
                for stmt in writer.pop(referent):
                    stmt.canonical_id = canonical_id
                    writer.add_statement(stmt)

    def close(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.dataset.name!r})>"


class Writer(Generic[DS, SE]):
    """Bulk writing operations."""

    def __init__(self, store: Store[DS, SE]):
        self.store = store

    def add_statement(self, stmt: Statement) -> None:
        raise NotImplementedError()

    def add_entity(self, entity: SE) -> None:
        for stmt in entity.statements:
            self.add_statement(stmt)

    def pop(self, entity_id: str) -> List[Statement]:
        raise NotImplementedError()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Writer[DS, SE]":
        return self

    def __exit__(
        self,
        type: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.flush()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.store!r})>"


class View(Generic[DS, SE]):
    def __init__(self, store: Store[DS, SE], scope: DS, external: bool = False):
        self.store = store
        self.scope = scope
        self.dataset_names = scope.leaf_names
        self.external = external

    def has_entity(self, id: str) -> bool:
        raise NotImplementedError()

    def get_entity(self, id: str) -> Optional[SE]:
        raise NotImplementedError()

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        raise NotImplementedError()

    def get_adjacent(
        self, entity: SE, inverted: bool = True
    ) -> Generator[Tuple[Property, SE], None, None]:
        for prop, value in entity.itervalues():
            if prop.type == registry.entity:
                child = self.get_entity(value)
                if child is not None:
                    yield prop, child

        if inverted and entity.id is not None:
            for prop, adjacent in self.get_inverted(entity.id):
                yield prop, adjacent

    def entities(self, include_schemata: List[Schema] = []) -> Generator[SE, None, None]:
        """Iterate over all entities in the view.

        If `include_schemata` is provided, only entities of the provided schemata will be returned.
        Note that `schemata` will not be expanded via "is_a" relationships."""

        raise NotImplementedError()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.scope.name!r})>"
