# Problem: undirected relationships in which both
# entities are given as the source AND the target
from nomenklatura.entity import CE
from nomenklatura.resolver import Identifier


def simplify_undirected(entity: CE) -> CE:
    if (
        not entity.schema.edge_source
        or not entity.schema.edge_target
        or entity.schema.edge_directed
    ):
        return entity
    source_ids = entity.get(entity.schema.edge_source)
    target_ids = entity.get(entity.schema.edge_target)
    if len(source_ids) < 2 and len(target_ids) < 2:
        return entity
    sources = [Identifier.get(s) for s in source_ids]
    targets = [Identifier.get(s) for s in target_ids]
    return entity
