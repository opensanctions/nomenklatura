from typing import Dict, Generator, Generic, Set
from followthemoney.types import registry

from nomenklatura.entity import CE
from nomenklatura.stream import StreamEntity
from nomenklatura.resolver.identifier import Identifier, StrIdent
from nomenklatura.statement.statement import Statement


class Linker(Generic[CE]):
    """A class to manage the canonicalisation of entities. This stores only the positive
    merges of entities and is used as a lightweight way to apply the harmonisation
    post de-duplication."""

    def __init__(self, entities: Dict[Identifier, Set[Identifier]] = {}) -> None:
        self._entities: Dict[Identifier, Set[Identifier]] = entities

    def connected(self, node: Identifier) -> Set[Identifier]:
        return self._entities.get(node, set([node]))

    def get_canonical(self, entity_id: StrIdent) -> str:
        """Return the canonical identifier for the given entity ID."""
        node = Identifier.get(entity_id)
        best = max(self.connected(node))
        if best.canonical:
            return best.id
        return node.id

    def canonicals(self) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        for node in self._entities.keys():
            if not node.canonical:
                continue
            canonical = self.get_canonical(node)
            if canonical == node.id:
                yield node

    def get_referents(
        self, canonical_id: StrIdent, canonicals: bool = True
    ) -> Set[str]:
        """Get all the non-canonical entity identifiers which refer to a given
        canonical identifier."""
        node = Identifier.get(canonical_id)
        referents: Set[str] = set()
        for connected in self.connected(node):
            if not canonicals and connected.canonical:
                continue
            if connected == node:
                continue
            referents.add(connected.id)
        return referents

    def apply(self, proxy: CE) -> CE:
        """Replace all entity references in a given proxy with their canonical
        identifiers. This is essentially the harmonisation post de-dupe."""
        if proxy.id is None:
            return proxy
        proxy.id = self.get_canonical(proxy.id)
        return self.apply_properties(proxy)

    def apply_stream(self, proxy: StreamEntity) -> StreamEntity:
        if proxy.id is None:
            return proxy
        proxy.id = self.get_canonical(proxy.id)
        for prop in proxy.iterprops():
            if prop.type == registry.entity:
                values = proxy.pop(prop)
                for value in values:
                    proxy.unsafe_add(prop, self.get_canonical(value), cleaned=True)
        return proxy

    def apply_properties(self, proxy: CE) -> CE:
        for stmt in proxy._iter_stmt():
            if proxy.id is not None:
                stmt.canonical_id = proxy.id
            if stmt.prop_type == registry.entity.name:
                canon_value = self.get_canonical(stmt.value)
                if canon_value != stmt.value:
                    if stmt.original_value is None:
                        stmt.original_value = stmt.value
                    # NOTE: this means the key is out of whack here now
                    stmt.value = canon_value
        return proxy

    def apply_statement(self, stmt: Statement) -> Statement:
        if stmt.entity_id is not None:
            stmt.canonical_id = self.get_canonical(stmt.entity_id)
        if stmt.prop_type == registry.entity.name:
            canon_value = self.get_canonical(stmt.value)
            if canon_value != stmt.value:
                if stmt.original_value is None:
                    stmt.original_value = stmt.value
                # NOTE: this means the key is out of whack here now
                stmt.value = canon_value
        return stmt

    def __repr__(self) -> str:
        return f"<Merger({len(self._entities)})>"
