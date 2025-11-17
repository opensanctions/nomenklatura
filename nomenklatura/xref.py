import logging
from typing import Callable, List, Optional, Type
from followthemoney import Schema, DS, SE
from pathlib import Path

from nomenklatura.store import Store
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.blocker import Index
from nomenklatura.matching import DefaultAlgorithm, ScoringAlgorithm, ScoringConfig

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
    resolver: Resolver[SE],
    store: Store[DS, SE],
    index_dir: Path,
    limit: int = 5000,
    limit_factor: int = 10,
    scored: bool = True,
    external: bool = True,
    discount_internal: float = 0.7,
    range: Optional[Schema] = None,
    auto_threshold: Optional[float] = None,
    focus_dataset: Optional[str] = None,
    algorithm: Type[ScoringAlgorithm] = DefaultAlgorithm,
    heuristic: Optional[
        Callable[[Resolver[SE], SE, SE, float], Optional[float]]
    ] = None,
    config: Optional[ScoringConfig] = None,
    user: Optional[str] = None,
) -> None:
    log.info("Begin xref: %r, resolver: %s", store, resolver)
    if config is None:
        config = ScoringConfig.defaults()
    view = store.default_view(external=external)
    index = Index(view, index_dir)
    index.build()

    try:
        scores: List[float] = []
        suggested = 0
        idx = 0
        resolver.begin()
        pairs = index.pairs(max_pairs=limit * limit_factor)
        for idx, ((left_id_, right_id_), score) in enumerate(pairs):
            if idx % 1000 == 0 and idx > 0:
                _print_stats(idx, suggested, scores)

            if suggested % 10000 == 0 and suggested > 0:
                resolver.commit()
                resolver.begin()

            left_id = resolver.get_canonical(left_id_)
            right_id = resolver.get_canonical(right_id_)
            if not resolver.check_candidate(left_id, right_id):
                continue

            left = view.get_entity(left_id)
            right = view.get_entity(right_id)
            if left is None or left.id is None or right is None or right.id is None:
                continue

            if not left.schema.can_match(right.schema):
                continue

            if focus_dataset is not None:
                if (
                    focus_dataset not in left.datasets
                    and focus_dataset not in right.datasets
                ):
                    continue

            if range is not None:
                if not left.schema.is_a(range) and not right.schema.is_a(range):
                    continue

            if scored:
                result = algorithm.compare(left, right, config)
                score = result.score
                if len(left.datasets.intersection(right.datasets)) > 0:
                    score = score * discount_internal

            if heuristic is not None:
                hscore = heuristic(resolver, left, right, score)
                if hscore is None:
                    continue
                score = hscore

            scores.append(score)

            if auto_threshold is not None and score > auto_threshold:
                log.info("Auto-merge [%.2f]: %s <> %s", score, left, right)
                canonical_id = resolver.decide(
                    left_id, right_id, Judgement.POSITIVE, user=user
                )
                store.update(canonical_id)
                continue

            resolver.suggest(left.id, right.id, score, user=user)

            if suggested >= limit:
                break
            suggested += 1
        _print_stats(idx, suggested, scores)
        resolver.commit()
    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")
