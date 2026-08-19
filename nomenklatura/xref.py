import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from followthemoney import DS, SE, Schema

from nomenklatura.blocker import Index
from nomenklatura.db import Session
from nomenklatura.judgement import Judgement
from nomenklatura.matching import DedupeAlgorithm, ScoringAlgorithm, ScoringConfig
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store

log = logging.getLogger(__name__)


def _print_stats(pairs: int, suggested: int, scores: list[float]) -> None:
    matches = len(scores)
    log.info(
        "Xref: %d pairs, %d scored, %d suggested, avg: %.2f, min: %.2f, max: %.2f",
        pairs,
        matches,
        suggested,
        sum(scores) / max(1, matches),
        min(scores, default=0.0),
        max(scores, default=0.0),
    )


def xref(
    resolver: Resolver[SE],
    session: Session,
    store: Store[DS, SE],
    index_dir: Path,
    limit: int = 5000,
    limit_factor: int = 10,
    patience: int = 500000,
    scored: bool = True,
    external: bool = True,
    discount_internal: float = 0.7,
    range: Schema | None = None,
    auto_threshold: float | None = None,
    min_threshold: float = 0.01,
    focus_datasets: set[str] | None = None,
    algorithm: type[ScoringAlgorithm] = DedupeAlgorithm,
    heuristic: Callable[[Resolver[SE], SE, SE, float], float | None] | None = None,
    config: ScoringConfig | None = None,
    blocker_options: dict[str, Any] | None = None,
    user: str | None = None,
) -> None:
    log.info(
        "Begin xref: %r, resolver: %s, limit: %d, patience: %d",
        store,
        resolver,
        limit,
        patience,
    )
    if config is None:
        config = ScoringConfig.defaults()
    view = store.default_view(external=external)
    index = Index(view, index_dir, options=blocker_options or {})
    index.build()
    max_pairs = limit * limit_factor
    # Patience is measured over scored pairs, not raw blocker ranks: pairs
    # skipped as already-decided are nearly free to pass over, and in mature
    # scopes hundreds of thousands of them can sit at the top of the ranking.
    last_suggested = 0

    try:
        scores: list[float] = []
        suggested = 0
        idx = 0
        resolver.load_into_memory()
        # Release the load transaction before the in-memory scan.
        session.checkpoint()
        pairs = index.pairs(max_pairs=max_pairs)
        for idx, ((left_id_, right_id_), score) in enumerate(pairs):
            if idx % 1000 == 0 and idx > 0:
                _print_stats(idx, suggested, scores)

            if idx > max_pairs:
                log.info("Reached maximum number of pairs to consider.")
                break

            if (len(scores) - last_suggested) > patience:
                log.info(
                    "No suggestions in the last %d scored pairs, stopping.", patience
                )
                break

            if suggested % 10000 == 0 and suggested > 0:
                session.checkpoint()

            left_id = resolver.get_canonical(left_id_.id)
            right_id = resolver.get_canonical(right_id_.id)
            if not resolver.check_candidate(left_id, right_id):
                continue

            left = view.get_entity(left_id)
            right = view.get_entity(right_id)
            if left is None or left.id is None or right is None or right.id is None:
                continue

            if not left.schema.can_match(right.schema):
                continue

            if focus_datasets:
                if left.datasets.isdisjoint(
                    focus_datasets
                ) and right.datasets.isdisjoint(focus_datasets):
                    continue

            if range is not None:
                if not left.schema.is_a(range) and not right.schema.is_a(range):
                    continue

            # Two pre-verification suggestions have nothing to anchor to each other;
            # xref should spend its budget expanding the graph instead.
            if left.external and right.external:
                continue

            if scored:
                score = algorithm.compare(left, right, config).score

            if len(left.datasets.intersection(right.datasets)) > 0:
                score = score * discount_internal

            if heuristic is not None:
                hscore = heuristic(resolver, left, right, score)
                if hscore is None:
                    continue
                score = hscore

            scores.append(score)

            if score < min_threshold:
                continue

            # Record this as a successful candidate:
            last_suggested = len(scores)

            if auto_threshold is not None and score > auto_threshold:
                log.info("Auto-merge [%.2f]: %s <> %s", score, left, right)
                canonical = resolver.decide(
                    left_id,
                    right_id,
                    Judgement.POSITIVE,
                    user=user,
                    score=score,
                )
                store.update(canonical.id)
                continue

            resolver.suggest(left.id, right.id, score, user=user)

            if suggested >= limit:
                break
            suggested += 1
        _print_stats(idx, suggested, scores)
        session.checkpoint()
    except KeyboardInterrupt:
        log.info("User cancelled, xref will end gracefully.")
    finally:
        index.close()
