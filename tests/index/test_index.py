from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

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


def test_index_build(index_path: Path, dstore: SimpleMemoryStore):
    index = Index(dstore.default_view(), index_path)
    assert len(index) == 0, index.fields
    assert len(index.fields) == 0, index.fields
    index.build()
    assert len(index) == 184, len(index)


def test_index_persist(dstore: SimpleMemoryStore, dindex):
    view = dstore.default_view()
    with TemporaryDirectory() as tmpdir:
        with NamedTemporaryFile("w") as fh:
            path = Path(fh.name)
            dindex.save(path)
            loaded = Index.load(dstore.default_view(), path, tmpdir)
    assert len(dindex.entities) == len(loaded.entities), (dindex, loaded)
    assert len(dindex) == len(loaded), (dindex, loaded)

    path.unlink(missing_ok=True)
    with TemporaryDirectory() as tmpdir:
        empty = Index.load(view, path, tmpdir)
        assert len(empty) == len(loaded), (empty, loaded)


def test_index_pairs(dstore: SimpleMemoryStore, dindex: Index):
    view = dstore.default_view()
    pairs = dindex.pairs()
    assert len(pairs) > 0, pairs
    tokenizer = dindex.tokenizer
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


def test_match_score(dstore: SimpleMemoryStore, dindex: Index):
    """Match an entity that isn't itself in the index"""
    dx = Dataset.make({"name": "test", "title": "Test"})
    entity = CompositeEntity.from_data(dx, VERBAND_BADEN_DATA)
    matches = dindex.match(entity)
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
    assert DAIMLER in dindex.entities
    assert DAIMLER not in match_identifiers


def test_top_match_matches_strong_pairs(dstore: SimpleMemoryStore, dindex: Index):
    """Pairs with high scores are each others' top matches"""

    view = dstore.default_view()
    strong_pairs = [p for p in dindex.pairs() if p[1] > 3.0]
    assert len(strong_pairs) > 4

    for pair, pair_score in strong_pairs:
        entity = view.get_entity(pair[0])
        matches = dindex.match(entity)
        # it'll match itself and the other in the pair
        for match, match_score in matches[:2]:
            assert match in pair, (match, pair)
