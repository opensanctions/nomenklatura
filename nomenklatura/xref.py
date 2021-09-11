from typing import Iterable
from nomenklatura.loader import DS, E
from nomenklatura.resolver import Resolver
from nomenklatura.index import Index


def xref(
    index: Index[DS, E], resolver: Resolver, entities: Iterable[E], limit: int = 15
) -> None:
    for query in entities:
        assert query.id is not None, query
        for match, score in index.match(query, limit=limit):
            assert match.id is not None, match
            resolver.suggest(query.id, match.id, score)
