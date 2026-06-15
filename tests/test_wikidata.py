import pytest
import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.cache import Cache
from nomenklatura.wikidata import LangText, WikidataClient
from nomenklatura.enrich.wikidata import clean_wikidata_name

from .conftest import wd_read_response


def test_lang_text():
    text1 = LangText("John Smith", "eng")
    text2 = LangText("John Smith", "ara")
    assert text1 != text2

    text2 = LangText("John Smith", "eng")
    assert text1 == text2


def test_model_apply():
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    ent = Entity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
    text = LangText("test", "en")
    text.apply(ent, "name")
    assert ent.get("name") == ["test"]

    only_dirty = LangText("(placeholder)", "en")
    only_dirty.apply(ent, "alias", clean=clean_wikidata_name)
    assert ent.get("alias") == ["(placeholder)"]
    ent.pop("alias")

    dirty = LangText("clean part (politician)", "en")
    dirty.apply(ent, "alias", clean=clean_wikidata_name)
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


def test_search_items(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    entity = Entity.from_data(
        dataset,
        {"schema": "Person", "id": "p1", "properties": {"name": ["Vladimir Putin"]}},
    )
    search = {
        "search": [
            {"id": "Q7747", "label": "Vladimir Putin"},
            {"id": "Q1058", "label": "someone else"},
            # Non-QID ids (e.g. property/lexeme hits) are filtered out:
            {"id": "P31", "label": "instance of"},
            {"label": "no id at all"},
        ]
    }
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=search)
        client = WikidataClient(test_cache)
        qids = client.search_items(entity)
        assert qids == ["Q7747", "Q1058"]

    # Empty result set: no `search` key returns no candidates and isn't cached.
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json={})
        client = WikidataClient(test_cache)
        empty = Entity.from_data(
            dataset,
            {"schema": "Person", "id": "p2", "properties": {"name": ["Nobody Here"]}},
        )
        assert client.search_items(empty) == []


def test_search_items_aliases(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    entity = Entity.from_data(
        dataset,
        {
            "schema": "Person",
            "id": "p3",
            "properties": {"name": ["Joe Biden"], "alias": ["Joseph Biden"]},
        },
    )

    def by_name(request, context):
        name = request.qs.get("search", [""])[0]
        if "joseph" in name:
            return {"search": [{"id": "Q6279"}, {"id": "Q12345"}]}
        return {"search": [{"id": "Q6279"}]}

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=by_name)
        client = WikidataClient(test_cache)
        # Default: only the name is searched, not the alias.
        assert client.search_items(entity) == ["Q6279"]
        # aliases=True also searches the alias; hits unioned, de-duplicated:
        assert client.search_items(entity, aliases=True) == ["Q6279", "Q12345"]


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
        assert len(item.sitelinks) > 2
        enwiki = [s for s in item.sitelinks if s.site == "enwiki"]
        assert len(enwiki) == 1
        assert enwiki[0].title == "Vladimir Putin"
        assert "Q5" in item.types
        birth_dates = [c for c in item.claims if c.property == "P569"]
        assert len(birth_dates) == 1
        assert birth_dates[0].text.text == "1952-10-07"
