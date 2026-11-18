import pytest
import requests_mock
from followthemoney import Dataset, StatementEntity

from nomenklatura.enrich import Enricher, make_enricher
from nomenklatura.enrich.openfigi import OpenFIGIEnricher

PATH = "nomenklatura.enrich.openfigi:OpenFIGIEnricher"
RESPONSE = {
    "data": [
        {
            "figi": "BBG0005S7P81",
            "securityType": "EURO-DOLLAR",
            "marketSector": "Govt",
            "ticker": "BKRUSS F 12/31/01",
            "name": "CENTRAL BANK OF RUSSIA",
            "exchCode": "NOT LISTED",
            "shareClassFIGI": None,
            "compositeFIGI": None,
            "securityType2": None,
            "securityDescription": "BKRUSS Float 12/31/01",
        },
        {
            "figi": "BBG002T3FYF0",
            "securityType": "Index",
            "marketSector": "Index",
            "ticker": "RCRAMAR",
            "name": "Bank of Russia Russia Central",
            "exchCode": None,
            "shareClassFIGI": None,
            "compositeFIGI": None,
            "securityType2": None,
            "securityDescription": "Bank of Russia Russia Central",
        },
    ]
}


dataset = Dataset.make({"name": "ext_open_figi", "title": "OpenFIGI"})


def load_enricher(cache_factory) -> Enricher[Dataset]:
    cache = cache_factory(dataset)
    return make_enricher(dataset, cache, {"type": PATH})


def test_figi_match(cache_factory):
    enricher = load_enricher(cache_factory)
    with requests_mock.Mocker(real_http=False) as m:
        m.post("/v3/search", json=RESPONSE)

        data = {
            "schema": "Company",
            "id": "xxx",
            "properties": {"name": ["Bank of Russia"]},
        }
        ent = StatementEntity.from_data(dataset, data)
        m_results = list(enricher.match(ent))
        assert len(m_results) == 2, m_results
        m1 = m_results[0]
        m2 = m_results[1]
        assert m1.get("name") == ["CENTRAL BANK OF RUSSIA"], m1
        assert m2.get("name") == ["Bank of Russia Russia Central"], m2

        e_results = list(enricher.expand(ent, m_results[0]))
        assert len(e_results) == 2, e_results
        assert e_results[1].get("ticker") == ["BKRUSS F 12/31/01"], e_results
        assert e_results[1].get("issuer") == [m_results[0].id], e_results
    enricher.close()


@pytest.mark.parametrize(
    "config,environment,expected_key",
    [
        pytest.param(
            {"api_key": "configured-key"},
            {},
            "configured-key",
            id="explicit-key",
        ),
        pytest.param(
            {"api_key": "configured-key"},
            {"OPENFIGI_API_KEY": "default-key"},
            "configured-key",
            id="explicit-key-overrides-default",
        ),
        pytest.param(
            {"api_key": "${CUSTOM_OPENFIGI_API_KEY}"},
            {
                "CUSTOM_OPENFIGI_API_KEY": "custom-key",
                "OPENFIGI_API_KEY": "default-key",
            },
            "custom-key",
            id="custom-environment-reference",
        ),
        pytest.param(
            {},
            {"OPENFIGI_API_KEY": "default-key"},
            "default-key",
            id="default-environment-key",
        ),
        pytest.param({}, {}, None, id="missing-key"),
    ],
)
@pytest.mark.parametrize("schema", ["Company", "Security"])
def test_figi_request_api_key(
    cache_factory,
    monkeypatch,
    config: dict[str, str],
    environment: dict[str, str],
    expected_key: str | None,
    schema: str,
):
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_OPENFIGI_API_KEY", raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    enricher = make_enricher(dataset, cache_factory(dataset), {"type": PATH, **config})
    if schema == "Company":
        url = OpenFIGIEnricher.SEARCH_URL
        response = {"data": []}
        properties = {"name": ["Example Company"]}
    else:
        url = OpenFIGIEnricher.MAPPING_URL
        response = []
        properties = {"isin": ["US0378331005"]}
    entity = StatementEntity.from_data(
        dataset, {"id": "test-security", "schema": schema, "properties": properties}
    )
    try:
        with requests_mock.Mocker(real_http=False) as mock:
            mock.post(url, json=response)
            assert list(enricher.match(entity)) == []
            assert mock.call_count == 1
            assert mock.last_request is not None
            headers = mock.last_request.headers
            if expected_key is None:
                assert "X-OPENFIGI-APIKEY" not in headers
            else:
                assert headers["X-OPENFIGI-APIKEY"] == expected_key
    finally:
        enricher.close()
