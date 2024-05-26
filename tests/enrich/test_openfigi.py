import requests_mock
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher
from nomenklatura.enrich.common import Enricher
from nomenklatura.entity import CompositeEntity


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


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert enricher_cls is not None
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_figi_match():
    enricher = load_enricher()
    with requests_mock.Mocker(real_http=False) as m:
        m.post("/v3/search", json=RESPONSE)

        data = {
            "schema": "Company",
            "id": "xxx",
            "properties": {"name": ["Bank of Russia"]},
        }
        ent = CompositeEntity.from_data(dataset, data)
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
