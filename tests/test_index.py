from pathlib import Path
from tempfile import NamedTemporaryFile
from followthemoney import model
from nomenklatura.index import Index


def test_index_build(dloader):
    index = Index(dloader)
    assert len(index) == 0, index.terms
    assert len(index.inverted) == 0, index.inverted
    index.build()
    assert len(index) == 95, len(index.terms)


def test_index_persist(dloader, dindex):
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        dindex.save(path)
        loaded = Index.load(dloader, path)
    assert len(dindex.inverted) == len(loaded.inverted), (dindex, loaded)
    assert len(dindex) == len(loaded), (dindex, loaded)

    path.unlink(missing_ok=True)
    empty = Index.load(dloader, path)
    assert len(empty) == len(loaded), (empty, loaded)


def test_index_search(dindex):
    query = model.make_entity("Person")
    query.add("name", "Susanne Klatten")
    results = list(dindex.match(query))
    assert len(results), len(results)
    first = results[0][0]
    assert first.schema == query.schema, first.schema
    assert "Klatten" in first.caption

    query = model.make_entity("Person")
    query.add("name", "Henry Ford")
    results = list(dindex.match(query))
    assert len(results), len(results)

    query = model.make_entity("Company")
    query.add("name", "Susanne Klatten")
    results = list(dindex.match(query))
    assert len(results), len(results)
    first = results[0][0]
    assert first.schema != model.get("Person")
    assert "Klatten" not in first.caption

    query = model.make_entity("Address")
    assert not query.schema.matchable
    query.add("full", "Susanne Klatten")
    results = list(dindex.match(query))
    assert 0 == len(results), len(results)
