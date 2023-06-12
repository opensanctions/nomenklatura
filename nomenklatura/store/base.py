from typing import Optional, Generator, List, Tuple, TypeVar, Generic
from followthemoney.property import Property

from nomenklatura.dataset import DS, Dataset
from nomenklatura.resolver import Resolver, StrIdent
from nomenklatura.statement import Statement
from nomenklatura.entity import CE, CompositeEntity


class Store(Generic[DS, CE]):
    """A data storage and retrieval mechanism for statement-based entity data. Essentially,
    this is a triple store which can be implemented using various backends."""

    def __init__(
        self,
        dataset: DS,
        resolver: Resolver[CE],
    ):
        self.dataset = dataset
        self.resolver = resolver

    def writer(self) -> "Writer[DS, CE]":
        raise NotImplementedError()

    def view(self, scope: DS, external: bool = False) -> "View[DS, CE]":
        raise NotImplementedError()

    def assemble(self, statements: List[Statement]) -> CE:
        return CompositeEntity.from_statements(statements)  # type: ignore

    def update(self, id: StrIdent) -> None:
        canonical_id = self.resolver.get_canonical(id)
        writer = self.writer()
        for referent in self.resolver.get_referents(canonical_id):
            for stmt in writer.pop(referent):
                stmt.canonical_id = canonical_id
                writer.add_statement(stmt)
        writer.flush()


class Writer(Generic[DS, CE]):
    """Bulk writing operations."""

    def __init__(self, store: Store[DS, CE]):
        self.store = store

    def add_statement(self, stmt: Statement) -> None:
        raise NotImplementedError()

    def add_entity(self, entity: CE) -> None:
        for stmt in entity.statements:
            self.add_statement(stmt)

    def pop(self, entity_id: str) -> List[Statement]:
        raise NotImplementedError()

    def flush(self) -> None:
        pass

    # def __enter__(self)


class View(Generic[DS, CE]):
    def __init__(self, store: Store[DS, CE], scope: DS, external: bool = False):
        self.store = store
        self.scope = scope
        self.scope_names = scope.scope_names
        self.external = external

    def get_entity(self, id: str) -> Optional[CE]:
        raise NotImplementedError()

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        raise NotImplementedError()

    def entities(self) -> Generator[CE, None, None]:
        raise NotImplementedError()

    def __repr__(self) -> str:
        return f"<View({self.scope!r})>"
