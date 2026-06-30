import requests_mock
from followthemoney import Dataset, StatementEntity
from nomenklatura.enrich import make_enricher, Enricher

from ..conftest import wd_read_response

PATH = "nomenklatura.enrich.wikidata:WikidataEnricher"
dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})


def load_enricher(cache_factory) -> Enricher[Dataset]:
    cache = cache_factory(dataset)
    return make_enricher(dataset, cache, {"type": PATH})


def test_wikidata_match(cache_factory):
    enricher = load_enricher(cache_factory)

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        ent = StatementEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        assert results[0].id == "Q7747", results[0]

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        data = {
            "schema": "Person",
            "id": "xxx",
            "properties": {"wikidataId": ["Q7747"]},
        }
        ent = StatementEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        res0 = results[0]
        assert res0.id == "Q7747", res0
        assert "Platov" in res0.get("weakAlias")
        assert "Владимир Владимирович Путин" in res0.get("alias")
        assert "Vladimir" in res0.get("firstName")
    enricher.close()


def test_wikidata_enrich(cache_factory):
    enricher = load_enricher(cache_factory)
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        ent = StatementEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
        adjacent = list(enricher.expand(ent, ent))
        assert len(adjacent) > 3, adjacent
    enricher.close()
