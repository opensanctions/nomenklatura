import logging
from importlib import import_module
from typing import Iterable, Generator, Optional, Type, cast

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
        for match in enricher.match_wrapped(entity):
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
    enricher: Enricher, resolver: Resolver[CE], entities: Iterable[CE]
) -> Generator[CE, None, None]:
    for entity in entities:
        for match in enricher.match_wrapped(entity):
            judgement = resolver.get_judgement(match.id, entity.id)
            if judgement != Judgement.POSITIVE:
                continue

            log.info("Enrich [%s]: %r", entity, match)
            for adjacent in enricher.expand_wrapped(entity, match):
                adjacent.datasets.add(enricher.dataset.name)
                adjacent = resolver.apply(adjacent)
                yield adjacent


def get_enricher(import_path: str) -> Optional[Type[Enricher]]:
    if ":" not in import_path:
        raise RuntimeError("Invalid import path: %r" % import_path)
    module_name, clazz_name = import_path.split(":", 1)
    module = import_module(module_name)
    clazz = getattr(module, clazz_name)
    if clazz is None or not issubclass(clazz, Enricher):
        raise RuntimeError("Invalid enricher: %r" % import_path)
    return cast(Type[Enricher], clazz)
