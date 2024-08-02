from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.index.tantivy_index import TantivyIndex
from nomenklatura.resolver.identifier import Identifier
from nomenklatura.store import SimpleMemoryStore
from nomenklatura.util import clean_text_basic

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
    field_values = [(fld, val) for fld, val in field_values if fld != "text"]
    assert len(field_values) == 5, field_values
    assert (
        "name",
        {"verband der metall und elektroindustrie baden wurttemberg"},
    ) in field_values, field_values
    assert ("country", {"de"}) in field_values, field_values
    assert (
        "address",
        {"lautenschlagerstr 20  70173 stuttgart"},
    ) in field_values, field_values
    assert ("identifier", {"AA123456789"}) in field_values, field_values
    assert ("date", {"2020", "2020-01-01"}) in field_values, field_values


def test_match_score(dstore: SimpleMemoryStore, tantivy_index: TantivyIndex):
    """Match an entity that isn't itself in the index"""
    dx = Dataset.make({"name": "test", "title": "Test"})
    entity = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    matches = tantivy_index.match(entity)
    view = dstore.default_view()

    assert len(matches) == 9, matches

    top_result = matches[0]
    assert top_result[0] == Identifier(VERBAND_BADEN_ID), top_result

    # Terms and phrase match
    assert 75 < top_result[1] < 125, matches
    # Terms but not phrase match
    assert 25 < matches[1][1] < 75, matches
    # lowest > threshold
    assert matches[-1][1] > 1, matches

    top_3 = {m[0] for m in matches[:3]}
    assert Identifier(VERBAND_ID) in top_3, matches

    top_10 = {m[0] for m in matches[:10]}
    # Daimler is in the index but not in the matches
    assert DAIMLER in {e.id for e in dstore.default_view().entities()}
    assert DAIMLER not in top_10, top_10


def test_index_pairs(dstore: SimpleMemoryStore, tantivy_index: TantivyIndex):
    view = dstore.default_view()
    pairs = tantivy_index.pairs()
    assert 474 < len(pairs) < 474 * 474, pairs

    schemata = set()
    for (left, right), score in pairs[:40]:
        entity0 = view.get_entity(left.id)
        entity1 = view.get_entity(right.id)
        # print("Match", entity0, entity1, score)
        tokens0 = set(clean_text_basic(entity0.caption).split(" "))
        tokens1 = set(clean_text_basic(entity1.caption).split(" "))
        overlap = tokens0.intersection(tokens1)
        # Matches should have some overlap. Coincidentally on fields used in the caption.
        assert len(overlap) > 0, overlap
        schemata.add(entity0.schema.name)
        assert left.id != right.id

    assert "Person" in schemata
    assert "Company" in schemata
    assert "Address" in schemata

    top_5 = {p[0] for p in pairs[:5]}

    # These score higher than VME, despite having 3 and 4 matching tokens
    # similarly to VME, because their matching tokens are rarer in the corpus
    # than VME's.

    # Herr Prof. Dr. Schnabel
    assert (
        Identifier("72fd7df14e87678c9c6dcebb3ef045d11343d64c"),
        Identifier("152da487401ef4547baf2d2bc95f884dc5f8bba0"),
    ) in top_5, top_5
    # Bayerische Motorenwerke (BMW) AG
    assert (
        Identifier("21cc81bf3b960d2847b66c6c862e7aa9b5e4f487"),
        Identifier("12570ee94b8dc23bcc080e887539d3742b2a5237"),
    ) in top_5, top_5

    top_20 = {p[0] for p in pairs[:20]}
    # Verband der Metallindustrie Baden-Württemberg
    verband_baden = (
        Identifier("cf9133952825afac1e654542a70ae7ed20dbfa7a"),
        Identifier(VERBAND_BADEN_ID),
    )
    assert verband_baden in top_20, top_20
    assert verband_baden not in top_5, top_5

    assert sorted(pairs, key=lambda p: p[1], reverse=True) == pairs


def test_name_variations(dstore: SimpleMemoryStore, tantivy_index: TantivyIndex):
    """
    More variations of the same name doesn't increase the score

    This is to make sure that entities where many similar but not identical
    names have been merged in don't end up bumping up scores of less relevant
    entities with similar names.
    """
    dx = Dataset.make({"name": "test", "title": "Test"})
    verband_baden = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    more_verband = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    names = more_verband.get("name")
    assert len(names) == 1
    name = names[0]
    more_verband.add("name", name.title())
    more_verband.add("name", [f"{name} {n}" for n in range(1, 10)])

    matches = tantivy_index.match(verband_baden)
    matches_more = tantivy_index.match(more_verband)

    assert len(matches) > 1, matches
    assert matches == matches_more, (matches, matches_more)
