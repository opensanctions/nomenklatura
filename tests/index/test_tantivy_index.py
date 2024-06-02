from pathlib import Path
from tempfile import NamedTemporaryFile

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
        "name": ["VERBAND DER METALL UND ELEKTROINDUSTRIE BADEN WURTTEMBERG"]
    },
}


def test_match_score(dstore: SimpleMemoryStore, tantivy_index: TantivyIndex):
    """Match an entity that isn't itself in the index"""
    dx = Dataset.make({"name": "test", "title": "Test"})
    entity = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    matches = tantivy_index.match(entity)
    # 9 entities in the index where some token in the query entity matches some
    # token in the index.
    assert len(matches) == 9, matches

    top_result = matches[0]
    assert top_result[0] == Identifier(VERBAND_BADEN_ID), top_result
    assert 17 < top_result[1] < 22, matches

    next_result = matches[1]
    assert next_result[0] == Identifier(VERBAND_ID), next_result
    assert 15 < next_result[1] < 17, matches

    match_identifiers = set(str(m[0]) for m in matches)
    assert VERBAND_ID in match_identifiers

    # Daimler is in the index but not in the matches
    assert DAIMLER in {e.id for e in dstore.default_view().entities()}
    assert DAIMLER not in match_identifiers
