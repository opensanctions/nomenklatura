import logging
from typing import List, Optional, Type
from followthemoney.schema import Schema
from pathlib import Path

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import Store
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.index import TantivyIndex, BaseIndex
from nomenklatura.matching import DefaultAlgorithm, ScoringAlgorithm
from nomenklatura.conflicting_match import ConflictingMatchReporter

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
    resolver: Resolver[CE],
    store: Store[DS, CE],
    index_dir: Path,
    limit: int = 5000,
    limit_factor: int = 10,
    scored: bool = True,
    external: bool = True,
    range: Optional[Schema] = None,
    auto_threshold: Optional[float] = None,
    conflicting_match_threshold: Optional[float] = None,
    focus_dataset: Optional[str] = None,
    algorithm: Type[ScoringAlgorithm] = DefaultAlgorithm,
    user: Optional[str] = None,
    index_class: Type[BaseIndex[DS, CE]] = TantivyIndex,
) -> None:
    log.info("Begin xref: %r, resolver: %s", store, resolver)
    view = store.default_view(external=external)
    index = index_class(view, index_dir)
    index.build()
    conflict_reporter = None
    if conflicting_match_threshold is not None:
        conflict_reporter = ConflictingMatchReporter(
            view, resolver, conflicting_match_threshold
        )

    try:
        scores: List[float] = []
        suggested = 0
        idx = 0
        pairs = index.pairs(max_pairs=limit * limit_factor)
        for idx, ((left_id, right_id), score) in enumerate(pairs):
            if idx % 1000 == 0 and idx > 0:
                _print_stats(idx, suggested, scores)

            if not resolver.check_candidate(left_id, right_id):
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

            if conflict_reporter is not None:
                conflict_reporter.check_match(result.score, left_id.id, right_id.id)

            # Not sure this is globally a good idea.
            if len(left.datasets.intersection(right.datasets)) > 0:
                score = score * 0.7

            if auto_threshold is not None and score > auto_threshold:
                log.info("Auto-merge [%.2f]: %s <> %s", score, left, right)
                canonical_id = resolver.decide(
                    left_id, right_id, Judgement.POSITIVE, user=user
                )
                store.update(canonical_id)
                continue

            if focus_dataset in left.datasets and focus_dataset not in right.datasets:
                score = (score + 1.0) / 2.0
            if focus_dataset not in left.datasets and focus_dataset in right.datasets:
                score = (score + 1.0) / 2.0

            resolver.suggest(left.id, right.id, score, user=user)
            if suggested >= limit:
                break
            suggested += 1
        _print_stats(idx, suggested, scores)

        if conflict_reporter is not None:
            conflict_reporter.report()

    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")
