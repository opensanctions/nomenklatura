from followthemoney import model
from nomenklatura.loader import FileLoader


DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"


def test_loader_init(donations_json, dloader):
    assert len(donations_json) == len(dloader)
    entities = [e for e in dloader]
    assert len(donations_json) == len(entities)


def test_get_entity(dloader: FileLoader):
    entity = dloader.get_entity("banana")
    assert entity is None, entity
    entity = dloader.get_entity(DAIMLER)
    assert entity is not None, entity
    assert "Daimler" in entity.caption, entity.caption
    assert len(entity.datasets) == 1
    ds = entity.datasets.pop()
    assert "donations" in ds, ds

    adjacent = list(dloader.get_adjacent(entity))
    assert len(adjacent) == 10, len(adjacent)
    schemata = [e.schema for (_, e) in adjacent]
    assert model.get("Payment") in schemata, set(schemata)
    assert model.get("Address") in schemata, set(schemata)
    assert model.get("Company") not in schemata, set(schemata)
