from typing import Iterable
from nomenklatura.loader import DS, E
from nomenklatura.graph import Graph
from nomenklatura.index import Index


def xref(index: Index[DS, E], graph: Graph, entities: Iterable[E], limit: int = 15):
    for query in entities:
        assert query.id is not None, query
        for match, score in index.match(query, limit=limit):
            assert match.id is not None, match
            graph.suggest(query.id, match.id, score)
