import logging
from typing import Iterable, List, Optional

from followthemoney.dedupe import Judgement
from followthemoney.schema import Schema

from nomenklatura.entity import DS, E
from nomenklatura.loader import Loader
from nomenklatura.resolver import Resolver
from nomenklatura.index import Index
from nomenklatura.matching import compare_scored

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
    loader: Loader[DS, E],
    resolver: Resolver[E],
    limit: int = 15,
    fuzzy: bool = False,
    range: Optional[Schema] = None,
    auto_threshold: Optional[float] = None,
) -> None:
    log.info("Begin xref: %r, resolver: %s", loader, resolver)
    index = Index(loader)
    index.build(fuzzy=fuzzy, adjacent=False)
    scores: List[float] = []
    num_entities = 0
    try:
        for num_entities, query in enumerate(loader):
            assert query.id is not None, query
            if not query.schema.matchable:
                continue
            if range is not None and not query.schema.is_a(range):
                continue
            for match, score in index.match_entities(query, limit=limit):
                assert match.id is not None, match.id
                if match.id == query.id:
                    continue
                # judgement = resolver.get_judgement(query.id, match.id)
                # if judgement in (Judgement.POSITIVE, Judgement.NEGATIVE):
                #     continue
                # log.info("[%.2f]-> %r x %r", score, query.id, match_id)
                result = compare_scored(query, match)
                score = result["score"]
                if auto_threshold is not None and score > auto_threshold:
                    log.info("Auto-merge [%.2f]: %s <> %s", score, query, match)
                    resolver.decide(query.id, match.id, Judgement.POSITIVE)
                    continue
                resolver.suggest(query.id, match.id, score)
                scores.append(score)

            if num_entities % 100 == 0 and num_entities > 0:
                _print_stats(num_entities, scores)
    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")

    _print_stats(num_entities, scores)
