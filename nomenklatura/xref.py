import logging
from typing import Iterable, List, Optional
from followthemoney.schema import Schema

from nomenklatura.entity import DS, E
from nomenklatura.resolver import Resolver
from nomenklatura.index import Index

log = logging.getLogger(__name__)


def _print_stats(num_entities: int, scores: List[float]) -> None:
    matches = len(scores)
    log.info(
        "Xref: %d entities, %d matches, avg: %.2f, min: %.2f, max: %.2f",
        num_entities,
        matches,
        sum(scores) / max(1, matches),
        min(scores, default=0.0),
        max(scores, default=0.0),
    )


def xref(
    index: Index[DS, E],
    resolver: Resolver[E],
    entities: Iterable[E],
    limit: int = 15,
    range: Optional[Schema] = None,
) -> None:
    log.info("Begin xref: %r, resolver: %s", index, resolver)
    scores: List[float] = []
    num_entities = 0
    try:
        for num_entities, query in enumerate(entities):
            assert query.id is not None, query
            if not query.schema.matchable:
                continue
            if range is not None and not query.schema.is_a(range):
                continue
            for match_id, score in index.match(query, limit=limit):
                assert match_id is not None, match_id
                if match_id == query.id:
                    continue
                # judgement = resolver.get_judgement(query.id, match.id)
                # if judgement in (Judgement.POSITIVE, Judgement.NEGATIVE):
                #     continue
                # log.info("[%.2f]-> %r x %r", score, query.id, match_id)
                resolver.suggest(query.id, match_id, score)
                scores.append(score)

            if num_entities % 100 == 0 and num_entities > 0:
                _print_stats(num_entities, scores)
    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")

    _print_stats(num_entities, scores)
