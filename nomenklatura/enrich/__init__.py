import logging
from importlib import import_module
from typing import Dict, Iterable, Generator, Optional, Type, cast

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.matching import DefaultAlgorithm
from nomenklatura.enrich.common import (
    Enricher,
    EnricherConfig,
    ItemEnricher,
    BulkEnricher,
)
from nomenklatura.enrich.common import EnrichmentAbort, EnrichmentException
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver

log = logging.getLogger(__name__)
__all__ = [
    "Enricher",
    "EnrichmentAbort",
    "EnrichmentException",
    "BulkEnricher",
    "make_enricher",
    "enrich",
    "match",
]


def make_enricher(
    dataset: DS, cache: Cache, config: EnricherConfig
) -> Optional[Enricher[DS]]:
    enricher_type = config.pop("type")
    if ":" not in enricher_type:
        raise RuntimeError("Invalid import path: %r" % enricher_type)
    module_name, clazz_name = enricher_type.split(":", 1)
    module = import_module(module_name)
    clazz = getattr(module, clazz_name)
    if clazz is None or not issubclass(clazz, Enricher):
        raise RuntimeError("Invalid enricher: %r" % enricher_type)
    enr_clazz = cast(Type[Enricher[DS]], clazz)
    return enr_clazz(dataset, cache, config)


# nk match -i entities.json -o entities-with-matches.json -r resolver.json
# then:
# nk dedupe -i entities-with-matches.json -r resolver.json
def match(
    enricher: Enricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    if isinstance(enricher, BulkEnricher):
        yield from get_bulk_matches(enricher, resolver, entities)
    elif isinstance(enricher, ItemEnricher):
        yield from get_itemwise_matches(enricher, resolver, entities)
    else:
        raise EnrichmentException("Invalid enricher type: %r" % enricher)


def get_itemwise_matches(
    enricher: ItemEnricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    for entity in entities:
        yield entity
        try:
            for match in enricher.match_wrapped(entity):
                match_result = match_item(entity, match, resolver, enricher.dataset)
                if match_result is not None:
                    yield match_result
        except EnrichmentException:
            log.exception("Failed to match: %r" % entity)


def get_bulk_matches(
    enricher: BulkEnricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    entity_lookup: Dict[str, CE] = {}
    for entity in entities:
        try:
            enricher.load_wrapped(entity)
            if entity.id is None:
                raise EnrichmentException("Entity has no ID: %r" % entity)
            if entity.id in entity_lookup:
                raise EnrichmentException("Duplicate entity ID: %r" % entity.id)
            entity_lookup[entity.id] = entity
        except EnrichmentException:
            log.exception("Failed to match: %r" % entity)
    for entity_id, candidate_set in enricher.candidates():
        entity = entity_lookup[entity_id.id]
        try:
            for match in enricher.match_candidates(entity, candidate_set):
                match_result = match_item(entity, match, resolver, enricher.dataset)
                if match_result is not None:
                    yield match_result
        except EnrichmentException:
            log.exception("Failed to match: %r" % entity)


def match_item(
    entity: CE, match: CE, resolver: Resolver[CE], dataset: DS
) -> Optional[CE]:
    if entity.id is None or match.id is None:
        return None
    if not resolver.check_candidate(entity.id, match.id):
        return None
    if not entity.schema.can_match(match.schema):
        return None
    result = DefaultAlgorithm.compare(entity, match)
    log.info("Match [%s]: %.2f -> %s", entity, result.score, match)
    resolver.suggest(entity.id, match.id, result.score)
    match.datasets.add(dataset.name)
    match = resolver.apply(match)
    return match


# nk enrich -i entities.json -r resolver.json -o combined.json
def enrich(
    enricher: Enricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    if isinstance(enricher, BulkEnricher):
        yield from get_bulk_enrichments(enricher, resolver, entities)
    elif isinstance(enricher, ItemEnricher):
        yield from get_itemwise_enrichments(enricher, resolver, entities)
    else:
        raise EnrichmentException("Invalid enricher type: %r" % enricher)


def get_itemwise_enrichments(
    enricher: ItemEnricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    for entity in entities:
        try:
            for match in enricher.match_wrapped(entity):
                yield from enrich_item(enricher, entity, match, resolver)
        except EnrichmentException:
            log.exception("Failed to enrich: %r" % entity)


def get_bulk_enrichments(
    enricher: BulkEnricher[DS], resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    entity_lookup: Dict[str, CE] = {}
    for entity in entities:
        try:
            enricher.load_wrapped(entity)
            if entity.id is None:
                raise EnrichmentException("Entity has no ID: %r" % entity)
            if entity.id in entity_lookup:
                raise EnrichmentException("Duplicate entity ID: %r" % entity.id)
            entity_lookup[entity.id] = entity
        except EnrichmentException:
            log.exception("Failed to match: %r" % entity)
    for entity_id, candidate_set in enricher.candidates():
        entity = entity_lookup[entity_id.id]
        try:
            for match in enricher.match_candidates(entity, candidate_set):
                yield from enrich_item(enricher, entity, match, resolver)
        except EnrichmentException:
            log.exception("Failed to enrich: %r" % entity)


def enrich_item(
    enricher: Enricher[DS], entity: CE, match: CE, resolver: Resolver[CE]
) -> Generator[CE, None, None]:
    if entity.id is None or match.id is None:
        return None
    judgement = resolver.get_judgement(match.id, entity.id)
    if judgement != Judgement.POSITIVE:
        return None

    log.info("Enrich [%s]: %r", entity, match)
    for adjacent in enricher.expand_wrapped(entity, match):
        adjacent.datasets.add(enricher.dataset.name)
        adjacent = resolver.apply(adjacent)
        yield adjacent
