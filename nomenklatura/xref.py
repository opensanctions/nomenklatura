import math
import logging
from typing import Iterable, List

# from followthemoney.dedupe.judgement import Judgement

from nomenklatura.loader import DS, E
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
    index: Index[DS, E], resolver: Resolver, entities: Iterable[E], limit: int = 15
) -> None:
    log.info("Begin xref: %r, resolver: %s", index, resolver)
    scores: List[float] = []
    try:
        for num_entities, query in enumerate(entities):
            assert query.id is not None, query
            for match, score in index.match(query, limit=limit):
                assert match.id is not None, match
                if match.id == query.id:
                    continue
                # judgement = resolver.get_judgement(query.id, match.id)
                # if judgement in (Judgement.POSITIVE, Judgement.NEGATIVE):
                #     continue
                # log.debug("[%.2f]-> %r x %r", score, query, match)
                resolver.suggest(query.id, match.id, score)
                scores.append(score)

            if num_entities % 100 == 0 and num_entities > 0:
                _print_stats(num_entities, scores)
    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")

    _print_stats(num_entities, scores)
