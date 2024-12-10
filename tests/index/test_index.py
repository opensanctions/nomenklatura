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

    # At least one pair is found
    assert len(pairs) > 0, len(pairs)

    # A pair has tokens which overlap
    tokenizer = dindex.tokenizer
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

    assert len(pairs) == 428, len(pairs)


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
