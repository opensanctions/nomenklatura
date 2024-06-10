from tempfile import NamedTemporaryFile
from pprint import pprint

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.index.tantivy_index import TantivyIndex
from nomenklatura.resolver.identifier import Identifier
from nomenklatura.store import SimpleMemoryStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
VERBAND_ID = "62ad0fe6f56dbbf6fee57ce3da76e88c437024d5"
VERBAND_BADEN_ID = "69401823a9f0a97cfdc37afa7c3158374e007669"
VERBAND_BADEN_DATA = {
    "id": "bla",
    "schema": "Company",
    "properties": {
        "name": ["VERBAND DER METALL UND ELEKTROINDUSTRIE BADEN WURTTEMBERG"],
        "country": ["de"],
        "address": ["Lautenschlagerstr. 20, 70173 Stuttgart"],
        "addressEntity": ["f5b4c7b1"],
        "registrationNumber": ["AA.:123456789"],
        "incorporationDate": ["2020-01-01"],
        "topics": ["corp.public"],
        "sourceUrl": ["https://www.somewhere.com"],
        "foo": ["bar"],
    },
}


def test_entity_fields(test_dataset: Dataset):
    verband_baden = CompositeEntity.from_data(test_dataset, VERBAND_BADEN_DATA)
    field_values = list(TantivyIndex.entity_fields(verband_baden))
    assert len(field_values) == 6, field_values
    assert (
        "name",
        "verband der metall und elektroindustrie baden wurttemberg",
    ) in field_values, field_values
    assert ("country", "de") in field_values, field_values
    assert (
        "address",
        "lautenschlagerstr 20  70173 stuttgart",
    ) in field_values, field_values
    assert ("identifier", "AA123456789") in field_values, field_values
    assert ("date", "2020") in field_values, field_values
    assert ("date", "2020-01-01") in field_values, field_values


def test_match_score(dstore: SimpleMemoryStore, tantivy_index: TantivyIndex):
    """Match an entity that isn't itself in the index"""
    dx = Dataset.make({"name": "test", "title": "Test"})
    entity = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    matches = tantivy_index.match(entity)

    assert len(matches) == 18, matches

    top_result = matches[0]
    assert top_result[0] == Identifier(VERBAND_BADEN_ID), top_result

    # Terms and phrase match
    assert 200 < top_result[1] < 300, matches
    # Terms but not phrase match
    assert 50 < matches[1][1] < 100, matches
    # lowest > threshold
    assert matches[-1][1] > 1, matches

    top_3 = {m[0] for m in matches[:3]}
    assert Identifier(VERBAND_ID) in top_3, matches

    top_10 = {m[0] for m in matches[:10]}
    # Daimler is in the index but not in the matches
    assert DAIMLER in {e.id for e in dstore.default_view().entities()}
    assert DAIMLER not in top_10, top_10
