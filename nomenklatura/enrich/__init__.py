import logging
from typing import Iterable, Generator, Optional, Type, cast
from pkg_resources import iter_entry_points

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.matching import compare_scored
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver, Identifier

log = logging.getLogger(__name__)
__all__ = ["Enricher", "make_enricher", "enrich", "match"]


def make_enricher(
    dataset: DS, cache: Cache, config: EnricherConfig
) -> Optional[Enricher]:
    enricher = get_enricher(config.pop("type"))
    if enricher is not None:
        return enricher(dataset, cache, config)
    return None


# nk match -i entities.json -o entities-with-matches.json -r resolver.json
# then:
# nk dedupe -i entities-with-matches.json -r resolver.json
def match(
    enricher: Enricher, resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    for entity in entities:
        yield entity
        for match in enricher.match(entity):
            if not resolver.check_candidate(entity.id, match.id):
                continue
            if not entity.schema.can_match(match.schema):
                continue
            result = compare_scored(entity, match)
            score = result["score"]
            log.info("Match [%s]: %.2f -> %s", entity, score, match)
            resolver.suggest(entity.id, match.id, score)
            match.datasets.add(enricher.dataset.name)
            match = resolver.apply(match)
            yield match


# nk enrich -i entities.json -r resolver.json -o combined.json
def enrich(
    enricher: Enricher,
    resolver: Resolver[CE],
    entities: Iterable[CE],
    expand: bool = True,
) -> Generator[CE, None, None]:
    for entity in entities:
        # Check if any positive matches:
        entity_id = Identifier.get(entity.id)
        connected = resolver.connected(entity_id)
        if len(connected) == 1:
            continue

        for match in enricher.match(entity):
            judgement = resolver.get_judgement(match.id, entity_id)
            if judgement != Judgement.POSITIVE:
                continue

            log.info("Enrich [%s]: %r", entity, match)
            if expand:
                for adjacent in enricher.expand(match):
                    adjacent.datasets.add(enricher.dataset.name)
                    adjacent = resolver.apply(adjacent)
                    yield adjacent

            match.datasets.add(enricher.dataset.name)
            match = resolver.apply(match)
            yield match


def get_enrichers() -> Generator[Type[Enricher], None, None]:
    for ep in iter_entry_points("nomenklatura.enrichers"):
        yield cast(Type[Enricher], ep.load())


def get_enricher(name: str) -> Optional[Type[Enricher]]:
    for ep in iter_entry_points("nomenklatura.enrichers"):
        if ep.name == name:
            return cast(Type[Enricher], ep.load())
    return None
