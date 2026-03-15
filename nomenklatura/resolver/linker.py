from typing import Dict, Generator, Generic, Set, Tuple
from followthemoney import registry, ValueEntity, Statement, SE

from nomenklatura.resolver.identifier import Identifier


class Linker(Generic[SE]):
    """A class to manage the canonicalisation of entities. This stores only the positive
    merges of entities and is used as a lightweight way to apply the harmonisation
    post de-duplication.

    Internally stores a dict[str, tuple[str, ...]] where each cluster is a sorted
    tuple with the canonical ID at index 0 and referents following. Every node in
    a cluster maps to the same shared tuple object."""

    def __init__(self, mapping: Dict[str, Tuple[str, ...]]) -> None:
        self._mapping: Dict[str, Tuple[str, ...]] = mapping

    def connected(self, node: Identifier) -> Set[Identifier]:
        """Return all entities connected to the given node. Constructs Identifier
        objects on the fly from the internal string representation."""
        cluster = self._mapping.get(node.id)
        if cluster is None:
            return {node}
        return {Identifier.get(n) for n in cluster}

    def connected_plain(self, node_id: str) -> Tuple[str, ...]:
        """Return all entity IDs connected to the given node ID. This is a more
        efficient version of `connected` which avoids constructing Identifier
        objects."""
        cluster = self._mapping.get(node_id)
        if cluster is None:
            return (node_id,)
        return cluster

    def get_canonical(self, entity_id: str) -> str:
        """Return the canonical identifier for the given entity ID."""
        if isinstance(entity_id, Identifier):
            entity_id = entity_id.id
        cluster = self._mapping.get(entity_id)
        if cluster is not None:
            return cluster[0]
        return entity_id

    def canonicals(self) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        seen: Set[str] = set()
        for cluster in self._mapping.values():
            canonical = cluster[0]
            if canonical not in seen:
                ident = Identifier.get(canonical)
                if ident.canonical:
                    seen.add(canonical)
                    yield ident

    def get_referents(self, canonical_id: str, canonicals: bool = True) -> Set[str]:
        """Get all the non-canonical entity identifiers which refer to a given
        canonical identifier."""
        if isinstance(canonical_id, Identifier):
            canonical_id = canonical_id.id
        cluster = self._mapping.get(canonical_id)
        if cluster is None:
            return set()
        referents = set(cluster)
        referents.discard(canonical_id)
        if not canonicals:
            referents = {r for r in referents if not Identifier.get(r).canonical}
        return referents

    def apply(self, proxy: SE) -> SE:
        """Replace all entity references in a given proxy with their canonical
        identifiers. This is essentially the harmonisation post de-dupe."""
        if proxy.id is None:
            return proxy
        proxy.id = self.get_canonical(proxy.id)
        return self.apply_properties(proxy)

    def apply_stream(self, proxy: ValueEntity) -> ValueEntity:
        if proxy.id is None:
            return proxy
        proxy.id = self.get_canonical(proxy.id)
        for prop in proxy.iterprops():
            if prop.type == registry.entity:
                values = proxy.pop(prop)
                for value in values:
                    proxy.unsafe_add(prop, self.get_canonical(value), cleaned=True)
        return proxy

    def apply_properties(self, proxy: SE) -> SE:
        for stmt in proxy._iter_stmt():
            if proxy.id is not None:
                stmt.canonical_id = proxy.id
            if stmt.prop_type == registry.entity.name:
                canon_value = self.get_canonical(stmt._value)
                if canon_value != stmt.value:
                    stmt = stmt.clone(
                        value=canon_value,
                        original_value=stmt.original_value or stmt._value,
                    )
        return proxy

    def apply_statement(self, stmt: Statement) -> Statement:
        if stmt.entity_id is not None:
            stmt.canonical_id = self.get_canonical(stmt.entity_id)
        if stmt.prop_type == registry.entity.name:
            canon_value = self.get_canonical(stmt._value)
            if canon_value != stmt._value:
                stmt = stmt.clone(
                    value=canon_value,
                    original_value=stmt.original_value or stmt._value,
                )
        return stmt

    def __repr__(self) -> str:
        return f"<Linker({len(self._mapping)})>"
