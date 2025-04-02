import pytest
import requests_mock

from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.wikidata import LangText, WikidataClient
from nomenklatura.enrich.wikidata import clean_name
from nomenklatura.entity import CompositeEntity

from .conftest import wd_read_response


def test_lang_text():
    text1 = LangText("John Smith", "eng")
    text2 = LangText("John Smith", "ara")
    assert text1 != text2

    text2 = LangText("John Smith", "eng")
    assert text1 == text2


def test_model_apply():
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    ent = CompositeEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
    text = LangText("test", "en")
    text.apply(ent, "name")
    assert ent.get("name") == ["test"]

    only_dirty = LangText("(placeholder)", "en")
    only_dirty.apply(ent, "alias", clean=clean_name)
    assert ent.get("alias") == ["(placeholder)"]
    ent.pop("alias")

    dirty = LangText("clean part (politician)", "en")
    dirty.apply(ent, "alias", clean=clean_name)
    assert ent.get("alias") == ["clean part"]
    ent.pop("alias")


def test_client_query(test_cache: Cache):
    data = {
        "head": {"vars": ["person"]},
        "results": {
            "bindings": [
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q23",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q42",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q76",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q80",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q91",
                    }
                },
            ]
        },
    }
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            WikidataClient.QUERY_API,
            json=data,
        )
        client = WikidataClient(test_cache)
        with pytest.raises(RuntimeError):
            client.query("  ")

        query = "SELECT ?person WHERE { ?person wdt:P31 wd:Q5 . } LIMIT 5"
        response = client.query(query)
        assert len(response) == 5
        assert "person" in repr(response)
        for result in response.results:
            assert "Q" in repr(result)
            assert len(result.values) == 1
            assert result.plain("person") is not None


def test_model(test_cache: Cache):
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            WikidataClient.WD_API,
            json=wd_read_response,
        )
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q7747")
        assert item is not None
        assert item.id == "Q7747"
        assert item.label is not None
        assert item.label.text == "Vladimir Putin"
        assert "Q5" in item.types
