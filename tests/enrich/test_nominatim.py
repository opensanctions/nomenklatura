from followthemoney import model
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher, enrich, match
from nomenklatura.enrich.common import Enricher
from nomenklatura.entity import CompositeEntity
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver

PATH = "nomenklatura.enrich.nominatim:NominatimEnricher"
dataset = Dataset("nominatim", "Nomimatim")


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_nominatim_match():
    enricher = load_enricher()

    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_dict(model, data)
    results = list(enricher.match(ent))
    assert len(results) == 1, results
    assert results[0].id == "osm-node-2140755199", results[0]

    full = "Jupiter Surface Space Station"
    data = {"schema": "Address", "id": "yyy", "properties": {"full": [full]}}
    ent = CompositeEntity.from_dict(model, data)
    results = list(enricher.match(ent))
    assert len(results) == 0, results


def test_nominatim_match_list():
    enricher = load_enricher()

    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_dict(model, data)

    resolver = Resolver()
    assert len(resolver.edges) == 0, resolver.edges
    results = list(match(enricher, resolver, [ent]))
    assert len(results) == 2, results
    assert len(resolver.edges) == 1, resolver.edges
    assert list(resolver.edges.values())[0].judgement == Judgement.NO_JUDGEMENT


def test_nominatim_enrich():
    enricher = load_enricher()
    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_dict(model, data)
    adjacent = list(enricher.expand(ent, ent))
    assert len(adjacent) == 1, adjacent


def test_nominatim_enrich_list():
    enricher = load_enricher()

    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_dict(model, data)

    resolver = Resolver()
    results = list(enrich(enricher, resolver, [ent]))
    assert len(results) == 0, results
    resolver.decide(ent.id, "osm-node-2140755199", judgement=Judgement.POSITIVE)
    results = list(enrich(enricher, resolver, [ent]))
    assert len(results) == 1, results
