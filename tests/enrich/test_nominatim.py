import requests_mock
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher, enrich, match
from nomenklatura.enrich.common import Enricher
from nomenklatura.entity import CompositeEntity
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver

PATH = "nomenklatura.enrich.nominatim:NominatimEnricher"
dataset = Dataset.make({"name": "nominatim", "title": "Nomimatim"})
RESPONSE = [
    {
        "place_id": 18513602,
        "licence": "Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright",
        "osm_type": "node",
        "osm_id": 2140755199,
        "boundingbox": ["52.548503", "52.548603", "13.403749", "13.403849"],
        "lat": "52.548553",
        "lon": "13.403799",
        "display_name": "47, Kopenhagener Straße, Gleimviertel, Prenzlauer Berg, Pankow, Berlin, 10437, Germany",
        "place_rank": 30,
        "category": "place",
        "type": "house",
        "importance": 0.4200099999999999,
        "address": {
            "house_number": "47",
            "road": "Kopenhagener Straße",
            "neighbourhood": "Gleimviertel",
            "suburb": "Prenzlauer Berg",
            "borough": "Pankow",
            "city": "Berlin",
            "ISO3166-2-lvl4": "DE-BE",
            "postcode": "10437",
            "country": "Germany",
            "country_code": "de",
        },
    },
    {
        "place_id": 35378943,
        "licence": "Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright",
        "osm_type": "node",
        "osm_id": 2952358136,
        "boundingbox": ["52.5776822", "52.5777822", "13.3611677", "13.3612677"],
        "lat": "52.5777322",
        "lon": "13.3612177",
        "display_name": "35;37;39;41;43;45;47;49;51;53;55;57, Kopenhagener Straße, Reinickendorf, Berlin, 13407, Germany",
        "place_rank": 30,
        "category": "place",
        "type": "house",
        "importance": 0.41000999999999993,
        "address": {
            "house_number": "35;37;39;41;43;45;47;49;51;53;55;57",
            "road": "Kopenhagener Straße",
            "suburb": "Reinickendorf",
            "borough": "Reinickendorf",
            "city": "Berlin",
            "ISO3166-2-lvl4": "DE-BE",
            "postcode": "13407",
            "country": "Germany",
            "country_code": "de",
        },
    },
]


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert enricher_cls is not None, PATH
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_nominatim_match():
    enricher = load_enricher()
    with requests_mock.Mocker(real_http=False) as m:
        m.get("/search.php", json=RESPONSE)
        full = "Kopenhagener Str. 47, Berlin"
        data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        assert results[0].id == "osm-node-2140755199", results[0]

        m.get("/search.php", json=[])
        full = "Jupiter Surface Space Station"
        data = {"schema": "Address", "id": "yyy", "properties": {"full": [full]}}
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 0, results


def test_nominatim_match_list():
    enricher = load_enricher()

    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_data(dataset, data)

    resolver = Resolver()
    assert len(resolver.edges) == 0, resolver.edges
    with requests_mock.Mocker(real_http=False) as m:
        m.get("/search.php", json=RESPONSE)
        results = list(match(enricher, resolver, [ent]))
    assert len(results) == 2, results
    assert len(resolver.edges) == 1, resolver.edges
    assert list(resolver.edges.values())[0].judgement == Judgement.NO_JUDGEMENT


def test_nominatim_enrich():
    enricher = load_enricher()
    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_data(dataset, data)
    with requests_mock.Mocker(real_http=False) as m:
        m.get("/search.php", json=RESPONSE)
        adjacent = list(enricher.expand(ent, ent))
    assert len(adjacent) == 1, adjacent


def test_nominatim_enrich_list():
    enricher = load_enricher()

    full = "Kopenhagener Str. 47, Berlin"
    data = {"schema": "Address", "id": "xxx", "properties": {"full": [full]}}
    ent = CompositeEntity.from_data(dataset, data)
    assert ent.id is not None, ent.id

    with requests_mock.Mocker(real_http=False) as m:
        m.get("/search.php", json=RESPONSE)
        resolver = Resolver()
        results = list(enrich(enricher, resolver, [ent]))
        assert len(results) == 0, results
        resolver.decide(ent.id, "osm-node-2140755199", judgement=Judgement.POSITIVE)
        results = list(enrich(enricher, resolver, [ent]))
        assert len(results) == 1, results
