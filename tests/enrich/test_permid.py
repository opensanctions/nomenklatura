import requests_mock
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher
from nomenklatura.enrich.common import Enricher
from nomenklatura.entity import CompositeEntity

PATH = "nomenklatura.enrich.permid:PermIDEnricher"
dataset = Dataset.make({"name": "permid", "title": "PermID"})
MATCH_ROSNEFT = {
    "ignore": "      ",
    "unMatched": 2,
    "matched": {"total": 2, "possible": 2},
    "numReceivedRecords": 3,
    "numProcessedRecords": 3,
    "numErrorRecords": 0,
    "headersIdentifiedSuccessfully": [
        "localid",
        "standard identifier",
        "name",
        "country",
    ],
    "headersNotIdentified": [],
    "headersSupportedWereNotSent": ["street", "city", "postalcode", "state", "website"],
    "errorCode": 0,
    "errorCodeMessage": "Success",
    "resolvingTimeInMs": 214,
    "requestTimeInMs": 214,
    "outputContentResponse": [
        {
            "ProcessingStatus": "OK",
            "Match Level": "No Match",
            "Original Row Number": "2",
            "Input_LocalID": "NK-3ZtG5jt3Xvm6QbW3KPqK99",
            "Input_Name": "NK Rosnaft' PAO",
            "Input_Country": "RU",
        },
        {
            "ProcessingStatus": "OK",
            "Match OpenPermID": "https://permid.org/1-4295887083",
            "Match OrgName": "NK Rosneft' PAO",
            "Match Score": "11%",
            "Match Level": "Possible",
            "Match Ordinal": "1",
            "Original Row Number": "3",
            "Input_LocalID": "NK-3ZtG5jt3Xvm6QbW3KPqK99",
            "Input_Name": "NK Rosneft' PAO",
            "Input_Country": "RU",
        },
    ],
}
MATCH_FAIL = {
    "ignore": "      ",
    "unMatched": 2,
    "matched": {"total": 2, "possible": 2},
    "numReceivedRecords": 3,
    "numProcessedRecords": 3,
    "numErrorRecords": 0,
    "headersIdentifiedSuccessfully": [
        "localid",
        "standard identifier",
        "name",
        "country",
    ],
    "headersNotIdentified": [],
    "headersSupportedWereNotSent": ["street", "city", "postalcode", "state", "website"],
    "errorCode": 0,
    "errorCodeMessage": "Success",
    "resolvingTimeInMs": 214,
    "requestTimeInMs": 214,
    "outputContentResponse": [
        {
            "ProcessingStatus": "OK",
            "Match Level": "No Match",
            "Original Row Number": "2",
            "Input_LocalID": "NK-3ZtG5jt3Xvm6QbW3KPqK99",
            "Input_Name": "NK Rosnaft' PAO",
            "Input_Country": "RU",
        },
        {
            "ProcessingStatus": "OK",
            "Match Level": "No Match",
            "Original Row Number": "3",
            "Input_LocalID": "NK-3ZtG5jt3Xvm6QbW3KPqK99",
            "Input_Name": "NK Rosneft' PAO",
            "Input_Country": "RU",
        },
    ],
}

ROSNEFT = {
    "@id": "https://permid.org/1-4295887083",
    "@type": "tr-org:Organization",
    "tr-common:hasPermId": "4295887083",
    "hasActivityStatus": "tr-org:statusActive",
    "hasHoldingClassification": "tr-org:publiclyHeld",
    "hasIPODate": "2006-07-17T04:00:00Z",
    "tr-org:hasLEI": "253400JT3MQWNDKMJE44",
    "hasLatestOrganizationFoundedDate": "2002-07-19T00:00:00Z",
    "isIncorporatedIn": "http://sws.geonames.org/2017370/",
    "isDomiciledIn": "http://sws.geonames.org/2017370/",
    "hasURL": "https://www.rosneft.ru/",
    "vcard:organization-name": "NK Rosneft' PAO",
    "@context": {
        "organization-name": {
            "@id": "http://www.w3.org/2006/vcard/ns#organization-name",
            "@type": "http://www.w3.org/2001/XMLSchema#string",
        },
        "hasHoldingClassification": {
            "@id": "http://permid.org/ontology/organization/hasHoldingClassification",
            "@type": "@id",
        },
        "hasActivityStatus": {
            "@id": "http://permid.org/ontology/organization/hasActivityStatus",
            "@type": "@id",
        },
        "hasLatestOrganizationFoundedDate": {
            "@id": "http://permid.org/ontology/organization/hasLatestOrganizationFoundedDate",
            "@type": "http://www.w3.org/2001/XMLSchema#dateTime",
        },
        "hasPermId": {
            "@id": "http://permid.org/ontology/common/hasPermId",
            "@type": "http://www.w3.org/2001/XMLSchema#string",
        },
        "hasLEI": {
            "@id": "http://permid.org/ontology/organization/hasLEI",
            "@type": "http://www.w3.org/2001/XMLSchema#string",
        },
        "hasIPODate": {
            "@id": "http://permid.org/ontology/organization/hasIPODate",
            "@type": "http://www.w3.org/2001/XMLSchema#dateTime",
        },
        "hasURL": {"@id": "http://www.w3.org/2006/vcard/ns#hasURL", "@type": "@id"},
        "isDomiciledIn": {
            "@id": "http://www.omg.org/spec/EDMC-FIBO/BE/LegalEntities/CorporateBodies/isDomiciledIn",
            "@type": "@id",
        },
        "isIncorporatedIn": {
            "@id": "http://permid.org/ontology/organization/isIncorporatedIn",
            "@type": "@id",
        },
        "tr-common": "http://permid.org/ontology/common/",
        "fibo-be-le-cb": "http://www.omg.org/spec/EDMC-FIBO/BE/LegalEntities/CorporateBodies/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "vcard": "http://www.w3.org/2006/vcard/ns#",
        "tr-org": "http://permid.org/ontology/organization/",
    },
}
GEONAME = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<rdf:RDF xmlns:cc="http://creativecommons.org/ns#" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:foaf="http://xmlns.com/foaf/0.1/" xmlns:gn="http://www.geonames.org/ontology#" xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:wgs84_pos="http://www.w3.org/2003/01/geo/wgs84_pos#">
    <gn:Feature rdf:about="https://sws.geonames.org/2017370/">
        <gn:name>Russia</gn:name>
        <gn:countryCode>RU</gn:countryCode>
    </gn:Feature>
</rdf:RDF>"""


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert enricher_cls is not None
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_permid_match():
    enricher = load_enricher()
    with requests_mock.Mocker(real_http=False) as m:
        m.post("/permid/match", json=MATCH_ROSNEFT)
        m.get("https://permid.org/1-4295887083", json=ROSNEFT)
        m.get("http://sws.geonames.org/2017370/about.rdf", text=GEONAME)
        data = {
            "schema": "Company",
            "id": "xxx",
            "properties": {"name": ["NK Rosneft' PAO"]},
        }
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        for res in results:
            assert res.id == "lei-253400JT3MQWNDKMJE44", res
            assert res.has("leiCode")
            assert res.has("name")

    with requests_mock.Mocker(real_http=False) as m:
        m.post("/permid/match", json=MATCH_FAIL)
        data = {
            "schema": "Company",
            "id": "yyy",
            "properties": {"name": ["Enron"]},
        }
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 0, results


def test_permid_enrich():
    enricher = load_enricher()
    with requests_mock.Mocker(real_http=False) as m:
        m.post("/permid/match", json=MATCH_ROSNEFT)
        m.get("https://permid.org/1-4295887083", json=ROSNEFT)
        m.get("http://sws.geonames.org/2017370/about.rdf", text=GEONAME)
        data = {
            "schema": "Company",
            "id": "zzz",
            "properties": {"name": ["NK Rosneft' PAO"]},
        }
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        for res in results:
            adjacent = list(enricher.expand(ent, res))
            assert len(adjacent) == 1, adjacent
            assert adjacent[0].id == "lei-253400JT3MQWNDKMJE44"
