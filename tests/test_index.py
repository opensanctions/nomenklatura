from pathlib import Path
from tempfile import NamedTemporaryFile

from nomenklatura.index import Index
from nomenklatura.store import SimpleMemoryStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"


def test_index_build(dstore: SimpleMemoryStore):
    index = Index(dstore.default_view())
    assert len(index) == 0, index.fields
    assert len(index.fields) == 0, index.fields
    index.build()
    assert len(index) == 184, len(index)


def test_index_persist(dstore: SimpleMemoryStore, dindex):
    view = dstore.default_view()
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        dindex.save(path)
        loaded = Index.load(dstore.default_view(), path)
    assert len(dindex.entities) == len(loaded.entities), (dindex, loaded)
    assert len(dindex) == len(loaded), (dindex, loaded)

    path.unlink(missing_ok=True)
    empty = Index.load(view, path)
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
