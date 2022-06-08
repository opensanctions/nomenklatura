import logging
from typing import List, Optional
from followthemoney.schema import Schema

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.loader import Loader
from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.index import Index
from nomenklatura.matching import compare_scored

# from nomenklatura.util import is_qid

log = logging.getLogger(__name__)


def _print_stats(pairs: int, suggested: int, scores: List[float]) -> None:
    matches = len(scores)
    log.info(
        "Xref: %d pairs, %d suggested, avg: %.2f, min: %.2f, max: %.2f",
        pairs,
        suggested,
        sum(scores) / max(1, matches),
        min(scores, default=0.0),
        max(scores, default=0.0),
    )


def xref(
    loader: Loader[DS, CE],
    resolver: Resolver[CE],
    limit: int = 5000,
    scored: bool = True,
    adjacent: bool = False,
    range: Optional[Schema] = None,
    auto_threshold: Optional[float] = None,
    user: Optional[str] = None,
) -> None:
    log.info("Begin xref: %r, resolver: %s", loader, resolver)
    index = Index(loader)
    index.build(adjacent=adjacent)
    try:
        scores: List[float] = []
        suggested = 0
        for idx, ((left_id, right_id), score) in enumerate(index.pairs()):
            if idx % 1000 == 0 and idx > 0:
                _print_stats(idx, suggested, scores)

            if not resolver.check_candidate(left_id, right_id):
                continue

            left = loader.get_entity(left_id.id)
            right = loader.get_entity(right_id.id)
            if left is None or right is None:
                continue

            if not left.schema.can_match(right.schema):
                continue

            if range is not None:
                if not left.schema.is_a(range) and not right.schema.is_a(range):
                    continue

            if scored:
                result = compare_scored(left, right)
                score = result["score"]
            scores.append(score)

            # if score > 0.985:
            #     if is_qid(left.id) and right.id.startswith("acf-"):
            #         print("LEFT", left, right)
            #         resolver.decide(left_id, right_id, Judgement.POSITIVE)
            #         continue
            #     if is_qid(right.id) and left.id.startswith("acf-"):
            #         print("RIGHT", left, right)
            #         resolver.decide(left_id, right_id, Judgement.POSITIVE)
            #         continue

            # Not sure this is globally a good idea.
            if len(left.datasets.intersection(right.datasets)) > 0:
                score = score * 0.7

            if auto_threshold is not None and score > auto_threshold:
                log.info("Auto-merge [%.2f]: %s <> %s", score, left, right)
                resolver.decide(left_id, right_id, Judgement.POSITIVE, user=user)
                continue
            resolver.suggest(left.id, right.id, score, user=user)
            if suggested > limit:
                break
            suggested += 1
        _print_stats(idx, suggested, scores)

    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")
