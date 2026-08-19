import logging
from collections.abc import Generator, Iterable
from importlib import import_module
from typing import cast

from followthemoney import DS, SE
from requests import Session

from nomenklatura.cache import Cache
from nomenklatura.enrich.common import (
    Enricher,
    EnricherConfig,
    EnrichmentAbort,
    EnrichmentException,
)
from nomenklatura.judgement import Judgement
from nomenklatura.matching import DefaultAlgorithm
from nomenklatura.matching.types import ScoringConfig
from nomenklatura.resolver import Resolver

log = logging.getLogger(__name__)
__all__ = [
    "Enricher",
    "EnrichmentAbort",
    "EnrichmentException",
    "enrich",
    "make_enricher",
    "match",
]


def make_enricher(
    dataset: DS,
    cache: Cache,
    config: EnricherConfig,
    http_session: Session | None = None,
) -> Enricher[DS]:
    """Instantiate the enricher class named by the `type` import path in the
    given configuration, e.g. `nomenklatura.enrich.wikidata:WikidataEnricher`."""
    enricher_type = config.pop("type")
    if ":" not in enricher_type:
        raise RuntimeError("Invalid import path: %r" % enricher_type)
    module_name, clazz_name = enricher_type.split(":", 1)
    module = import_module(module_name)
    clazz = getattr(module, clazz_name)
    if clazz is None or not issubclass(clazz, Enricher):
        raise RuntimeError("Invalid enricher: %r" % enricher_type)
    enr_clazz = cast("type[Enricher[DS]]", clazz)
    return enr_clazz(dataset, cache, config, session=http_session)


def match(
    enricher: Enricher[DS],
    resolver: Resolver[SE],
    entities: Iterable[SE],
    config: ScoringConfig | None = None,
) -> Generator[SE, None, None]:
    """Stream entities through the enricher and record candidate matches in
    the resolver.

    Yields each input entity, followed by the candidates found for it. Each
    candidate pair is scored and stored in the resolver as a suggestion, to be
    confirmed or rejected in a later review step (e.g. `nk dedupe`)."""
    if config is None:
        config = ScoringConfig.defaults()
    for entity in entities:
        yield entity
        try:
            for match in enricher.match_wrapped(entity):
                if entity.id is None or match.id is None:
                    continue
                if not resolver.check_candidate(entity.id, match.id):
                    continue
                if not entity.schema.can_match(match.schema):
                    continue
                result = DefaultAlgorithm.compare(entity, match, config)
                log.info("Match [%s]: %.2f -> %s", entity, result.score, match)
                resolver.suggest(entity.id, match.id, result.score)
                match.datasets.add(enricher.dataset.name)
                match = resolver.apply(match)
                yield match
        except EnrichmentException:
            log.exception("Failed to match: %r" % entity)


def enrich(
    enricher: Enricher[DS], resolver: Resolver[SE], entities: Iterable[SE]
) -> Generator[SE, None, None]:
    """Fetch data for entities whose matches have been confirmed.

    For each candidate that the resolver holds a positive judgement on, yields
    the matched entity and its related records from the enrichment source. Run
    this after judging the suggestions recorded by `match()`."""
    for entity in entities:
        try:
            for match in enricher.match_wrapped(entity):
                if entity.id is None or match.id is None:
                    continue
                judgement = resolver.get_judgement(match.id, entity.id)
                if judgement != Judgement.POSITIVE:
                    continue

                log.info("Enrich [%s]: %r", entity, match)
                for adjacent in enricher.expand_wrapped(entity, match):
                    adjacent.datasets.add(enricher.dataset.name)
                    adjacent = resolver.apply(adjacent)
                    yield adjacent
        except EnrichmentException:
            log.exception("Failed to enrich: %r" % entity)
