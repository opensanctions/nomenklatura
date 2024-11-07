from collections import defaultdict
from pathlib import Path

from nomenklatura.index import get_index
from nomenklatura.index.duckdb_index import DuckDBIndex
from nomenklatura.resolver.identifier import Identifier
from nomenklatura.store import SimpleMemoryStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
VERBAND_ID = "62ad0fe6f56dbbf6fee57ce3da76e88c437024d5"
VERBAND_BADEN_ID = "69401823a9f0a97cfdc37afa7c3158374e007669"
VERBAND_BADEN_DATA = {
    "id": "bla",
    "schema": "Company",
    "properties": {
        "name": ["VERBAND DER METALL UND ELEKTROINDUSTRIE BADEN WURTTEMBERG"]
    },
}


def test_import(dstore: SimpleMemoryStore, index_path: Path):
    view = dstore.default_view()
    index = get_index(view, index_path, "duckdb")
    assert isinstance(index, DuckDBIndex), type(index)


def test_field_lengths(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    field_names = set()
    ids = set()
    for field_name, id, field_len in duckdb_index.field_len_rel().fetchall():
        field_names.add(field_name)
        ids.add(id)

    # Expect to see all matchable entities
    # jq .schema tests/fixtures/donations.ijson | sort | uniq -c
    # Organizations 17
    # Companies 56
    # Persons 22
    # Addresses 89
    assert len(ids) == 184, len(ids)

    # Expect to see all index fields for the matchable prop types and any applicable synthetic fields
    # jq '.properties | keys | .[]' tests/fixtures/donations.ijson --raw-output|sort -u
    expected_fields = {
        "namepart",
        "name",
        "country",
        "word",
    }
    assert field_names == expected_fields, field_names


def test_mentions(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    ids = set()
    field_tokens = defaultdict(set)

    for field_name, id, token, count in duckdb_index.mentions_rel().fetchall():
        ids.add(id)
        field_tokens[field_name].add(token)

    assert len(ids) == 184, len(ids)
    assert "verband" in field_tokens["namepart"], field_tokens["namepart"]
    assert "gb" in field_tokens["country"], field_tokens["country"]
    assert "adolf wurth gmbh" in field_tokens["name"], field_tokens["name"]
    assert "dortmund" in field_tokens["word"], field_tokens["word"]


def test_index_pairs(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    view = dstore.default_view()
    pairs = list(duckdb_index.pairs())

    # At least one pair is found
    assert len(pairs) > 0, len(pairs)

    # A pair has tokens which overlap
    tokenizer = duckdb_index.tokenizer
    pair, score = pairs[0]
    entity0 = view.get_entity(str(pair[0]))
    tokens0 = set(tokenizer.entity(entity0))
    entity1 = view.get_entity(str(pair[1]))
    tokens1 = set(tokenizer.entity(entity1))
    overlap = tokens0.intersection(tokens1)
    assert len(overlap) > 0, overlap

    # A pair has non-zero score
    assert score > 0

    # pairs are in descending score order
    last_score = pairs[0][1]
    for pair in pairs[1:]:
        assert pair[1] <= last_score
        last_score = pair[1]

    #  Johanna Quandt <> Frau Johanna Quandt
    jq = (
        Identifier.get("9add84cbb7bb48c7552f8ec7ae54de54eed1e361"),
        Identifier.get("2d3e50433e36ebe16f3d906b684c9d5124c46d76"),
    )
    jq_score = [score for pair, score in pairs if jq == pair][0]

    #  Bayerische Motorenwerke AG <> Bayerische Motorenwerke (BMW) AG
    bmw = (
        Identifier.get("21cc81bf3b960d2847b66c6c862e7aa9b5e4f487"),
        Identifier.get("12570ee94b8dc23bcc080e887539d3742b2a5237"),
    )
    bmw_score = [score for pair, score in pairs if bmw == pair][0]

    # More tokens in BMW means lower TF, reducing the score
    assert jq_score > bmw_score, (jq_score, bmw_score)
    assert jq_score == 19.0, jq_score
    assert 3.3 < bmw_score < 3.4, bmw_score

    # FERRING Arzneimittel GmbH <> Clou Container Leasing GmbH
    false_pos = (
        Identifier.get("f8867c433ba247cfab74096c73f6ff5e36db3ffe"),
        Identifier.get("a061e760dfcf0d5c774fc37c74937193704807b5"),
    )
    false_pos_score = [score for pair, score in pairs if false_pos == pair][0]
    assert 1.1 < false_pos_score < 1.2, false_pos_score
    assert bmw_score > false_pos_score, (bmw_score, false_pos_score)
