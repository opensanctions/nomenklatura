from followthemoney import model
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher
from nomenklatura.enrich.common import Enricher
from nomenklatura.entity import CompositeEntity

PATH = "nomenklatura.enrich.wikidata:WikidataEnricher"
dataset = Dataset("wikidata", "Wikidata")


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_wikidata_match():
    enricher = load_enricher()

    ent = CompositeEntity.from_dict(model, {"schema": "Person", "id": "Q7747"})
    results = list(enricher.match(ent))
    assert len(results) == 1, results
    assert results[0].id == "Q7747", results[0]

    data = {"schema": "Person", "id": "xxx", "properties": {"wikidataId": ["Q7747"]}}
    ent = CompositeEntity.from_dict(model, data)
    results = list(enricher.match(ent))
    assert len(results) == 1, results
    assert results[0].id == "Q7747", results[0]


def test_wikidata_enrich():
    enricher = load_enricher()
    ent = CompositeEntity.from_dict(model, {"schema": "Person", "id": "Q7747"})
    adjacent = list(enricher.expand(ent, ent))
    assert len(adjacent) > 3, adjacent
