import requests_mock

from nomenklatura.cache import Cache
from nomenklatura.wikidata import LangText, WikidataClient


def test_lang_text():
    text1 = LangText("John Smith", "en")
    text2 = LangText("John Smith", "ar")
    assert text1 != text2
    assert text1 > text2

    text3 = LangText("Abigail Smith", "en")
    assert text1 != text3
    assert text1 > text3

    text2 = LangText("John Smith")
    assert text1 != text2
    assert text1 > text2


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
        query = "SELECT ?person WHERE { ?person wdt:P31 wd:Q5 . } LIMIT 5"
        response = client.query(query)
        assert len(response.results) == 5
        for result in response.results:
            assert len(result.values) == 1
            assert result.plain("person") is not None
