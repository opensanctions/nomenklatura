from nomenklatura.entity import CE
from nomenklatura.resolver import Identifier


def simplify_undirected(entity: CE) -> CE:
    """Simplify undirected edges by removing duplicate entity IDs on both
    ends."""
    # Problem: undirected relationships in which both
    # entities are given as the source AND the target
    if (
        not entity.schema.edge
        or entity.schema.edge_directed
        or not entity.schema.edge_source
        or not entity.schema.edge_target
    ):
        return entity
    sources = entity.get_statements(entity.schema.edge_source)
    targets = entity.get_statements(entity.schema.edge_target)
    source_ids = set((s.value for s in sources))
    target_ids = set((t.value for t in targets))
    common = source_ids.intersection(target_ids)
    if len(common) != 2:
        return entity
    identifiers = [Identifier.get(s) for s in common]
    source_id, target_id = max(identifiers), min(identifiers)
    for stmt in sources:
        if stmt.value == target_id:
            entity._statements[entity.schema.edge_source].remove(stmt)
    for stmt in targets:
        if stmt.value == source_id:
            entity._statements[entity.schema.edge_target].remove(stmt)
    return entity
