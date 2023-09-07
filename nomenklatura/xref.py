import logging
from typing import List, Optional, Type
from followthemoney.schema import Schema

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import Store
from nomenklatura.judgement import Judgement
from nomenklatura.index import Index
from nomenklatura.matching import DefaultAlgorithm, ScoringAlgorithm

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
    store: Store[DS, CE],
    limit: int = 5000,
    scored: bool = True,
    external: bool = True,
    range: Optional[Schema] = None,
    auto_threshold: Optional[float] = None,
    focus_dataset: Optional[str] = None,
    algorithm: Type[ScoringAlgorithm] = DefaultAlgorithm,
    user: Optional[str] = None,
) -> None:
    log.info("Begin xref: %r, resolver: %s", store, store.resolver)
    view = store.default_view(external=external)
    index = Index(view)
    index.build()
    try:
        scores: List[float] = []
        suggested = 0
        idx = 0
        for idx, ((left_id, right_id), score) in enumerate(index.pairs()):
            if idx % 1000 == 0 and idx > 0:
                _print_stats(idx, suggested, scores)

            if not store.resolver.check_candidate(left_id, right_id):
                continue

            left = view.get_entity(left_id.id)
            right = view.get_entity(right_id.id)
            if left is None or left.id is None or right is None or right.id is None:
                continue

            if not left.schema.can_match(right.schema):
                continue

            if range is not None:
                if not left.schema.is_a(range) and not right.schema.is_a(range):
                    continue

            if scored:
                result = algorithm.compare(left, right)
                score = result.score
            scores.append(score)

            # Not sure this is globally a good idea.
            if len(left.datasets.intersection(right.datasets)) > 0:
                score = score * 0.7

            if auto_threshold is not None and score > auto_threshold:
                log.info("Auto-merge [%.2f]: %s <> %s", score, left, right)
                canonical_id = store.resolver.decide(
                    left_id, right_id, Judgement.POSITIVE, user=user
                )
                store.update(canonical_id)
                continue

            if focus_dataset in left.datasets and focus_dataset not in right.datasets:
                score = (score + 1.0) / 2.0
            if focus_dataset not in left.datasets and focus_dataset in right.datasets:
                score = (score + 1.0) / 2.0

            store.resolver.suggest(left.id, right.id, score, user=user)
            if suggested >= limit:
                break
            suggested += 1
        _print_stats(idx, suggested, scores)

    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")
