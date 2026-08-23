from collections.abc import Generator, Iterable
from types import TracebackType
from typing import Generic, cast

from followthemoney import (
    DS,
    SE,
    Property,
    Schema,
    Statement,
    StatementEntity,
    registry,
)
from followthemoney.statement.util import get_prop_type

from nomenklatura.resolver import Linker


class Store(Generic[DS, SE]):
    """A data storage and retrieval mechanism for statement-based entity data.
    Essentially, this is a triple store which can be implemented using various
    backends."""

    def __init__(self, dataset: DS, linker: Linker[SE]):
        self.dataset = dataset
        self.linker = linker
        self.entity_class = cast("type[SE]", StatementEntity)

    def writer(self) -> "Writer[DS, SE]":
        raise NotImplementedError

    def view(self, scope: DS, external: bool = False) -> "View[DS, SE]":
        raise NotImplementedError

    def default_view(self, external: bool = False) -> "View[DS, SE]":
        return self.view(self.dataset, external=external)

    def assemble(self, statements: list[Statement]) -> SE | None:
        if not len(statements):
            return None
        canonicals: list[Statement] = []
        for stmt in statements:
            if get_prop_type(stmt.schema, stmt.prop) == registry.entity.name:
                ov = stmt._value if stmt.original_value is None else stmt.original_value
                stmt = stmt.clone(
                    value=self.linker.get_canonical(stmt._value),
                    original_value=ov,
                )
            canonicals.append(stmt)
        entity = self.entity_class.from_statements(self.dataset, canonicals)
        if entity.id is not None:
            entity.extra_referents.update(self.linker.get_referents(entity.id))
        return entity

    def update(self, id: str) -> None:
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
        raise NotImplementedError

    def add_entity(self, entity: SE) -> None:
        for stmt in entity.statements:
            self.add_statement(stmt)

    def pop(self, entity_id: str) -> list[Statement]:
        raise NotImplementedError

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Writer[DS, SE]":
        return self

    def __exit__(
        self,
        type: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.flush()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.store!r})>"


class View(Generic[DS, SE]):
    """Read access to the entities in a store, scoped to a dataset.

    Entities come back in their merged, canonical form. Use `get_entity()` for
    a lookup by ID, `entities()` to stream the whole scope, and `get_adjacent()`
    to traverse relationships in both directions.

    Statements marked `external` (enrichment candidates not yet accepted into
    the dataset) are excluded from all reads unless the view is constructed
    with `external=True`; an entity backed only by external statements is
    absent from an `external=False` view."""

    def __init__(self, store: Store[DS, SE], scope: DS, external: bool = False):
        self.store = store
        self.scope = scope
        self.dataset_names = scope.leaf_names
        self.external = external

    def has_entity(self, id: str) -> bool:
        raise NotImplementedError

    def get_entity(self, id: str) -> SE | None:
        raise NotImplementedError

    def get_entities(self, ids: Iterable[str]) -> Generator[SE, None, None]:
        """Fetch several entities in one go.

        Bulk readers (e.g. the xref scoring loop) should prefer this over
        repeated `get_entity()` calls so that stores backed by query engines
        can serve the batch from a single query."""
        for id in ids:
            entity = self.get_entity(id)
            if entity is not None:
                yield entity

    def get_inverted(self, id: str) -> Generator[tuple[Property, SE], None, None]:
        raise NotImplementedError

    def get_adjacent(
        self, entity: SE, inverted: bool = True
    ) -> Generator[tuple[Property, SE], None, None]:
        for prop, value in entity.itervalues():
            if prop.type == registry.entity:
                child = self.get_entity(value)
                if child is not None:
                    yield prop, child

        if inverted and entity.id is not None:
            for prop, adjacent in self.get_inverted(entity.id):
                yield prop, adjacent

    def entities(
        self,
        include_schemata: list[Schema] | None = None,
        prefetch_nested: bool = False,
    ) -> Generator[SE, None, None]:
        """Iterate over all entities in the view.

        If `include_schemata` is provided, only entities of the provided schemata will be returned.
        Note that `schemata` will not be expanded via "is_a" relationships.

        With `prefetch_nested`, implementations may bulk-load the adjacency of
        the scanned entities so that `get_entity`, `get_inverted` and
        `get_adjacent` calls made while iterating avoid per-call lookups.
        Point-read stores ignore the flag; results are identical either way."""

        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.scope.name!r})>"
