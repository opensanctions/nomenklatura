from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.index import Index
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


def test_field_lengths(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    field_names = set()
    ids = set()
    for field_name, id, field_len in duckdb_index.field_lengths():
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

    for field_name, id, token, count in duckdb_index.mentions():
        ids.add(id)
        field_tokens[field_name].add(token)

    assert len(ids) == 184, len(ids)
    assert "verband" in field_tokens["namepart"], field_tokens["namepart"]
    assert "de" in field_tokens["country"], field_tokens["country"]
    assert "adolf wurth gmbh" in field_tokens["name"], field_tokens["name"]
    assert "dortmund" in field_tokens["word"], field_tokens["word"]


def test_id_grouped_mentions(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    ids = set()
    field_tokens = defaultdict(set)
    for field_name, id, field_len, mentions in duckdb_index.id_grouped_mentions():
        ids.add(id)
        for token, count in mentions:
            field_tokens[field_name].add(token)

    assert len(ids) == 184, len(ids)
    assert "verband" in field_tokens["namepart"], field_tokens["namepart"]
    assert "de" in field_tokens["country"], field_tokens["country"]
    assert "adolf wurth gmbh" in field_tokens["name"], field_tokens["name"]
    assert "dortmund" in field_tokens["word"], field_tokens["word"]


def test_index_pairs(dstore: SimpleMemoryStore, duckdb_index: DuckDBIndex):
    view = dstore.default_view()
    pairs = duckdb_index.pairs()
    assert len(pairs) > 0, pairs
    tokenizer = duckdb_index.tokenizer
    pair, score = pairs[0]
    entity0 = view.get_entity(str(pair[0]))
    tokens0 = set(tokenizer.entity(entity0))
    entity1 = view.get_entity(str(pair[1]))
    tokens1 = set(tokenizer.entity(entity1))
    overlap = tokens0.intersection(tokens1)
    assert len(overlap) > 0, overlap
    # assert "Schnabel" in (overlap, tokens0, tokens1)
    # assert "Schnabel" in (entity0.caption, entity1.caption)
    assert score > 0
    # assert False
