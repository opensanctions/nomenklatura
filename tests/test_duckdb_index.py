from pathlib import Path
from tempfile import NamedTemporaryFile

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.index import Index
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


def test_match_score(dstore: SimpleMemoryStore, duckdb_index: Index):
    """Match an entity that isn't itself in the index"""
    dx = Dataset.make({"name": "test", "title": "Test"})
    entity = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    matches = duckdb_index.match(entity)
    # 9 entities in the index where some token in the query entity matches some
    # token in the index.
    assert len(matches) == 9, matches

    top_result = matches[0]
    assert top_result[0] == Identifier(VERBAND_BADEN_ID), top_result
    assert 1.99 < top_result[1] < 2, top_result

    next_result = matches[1]
    assert next_result[0] == Identifier(VERBAND_ID), next_result
    assert 1.66 < next_result[1] < 1.67, next_result

    match_identifiers = set(str(m[0]) for m in matches)
    assert VERBAND_ID in match_identifiers  # validity
    assert DAIMLER not in match_identifiers
