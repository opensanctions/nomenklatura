import pytest
from followthemoney import model
from nomenklatura.loader import FileLoader


DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"


@pytest.mark.asyncio
async def test_loader_init(donations_json, dloader):
    assert len(donations_json) == await dloader.count()
    entities = [e async for e in dloader.entities()]
    assert len(donations_json) == len(entities)


@pytest.mark.asyncio
async def test_get_entity(dloader: FileLoader):
    entity = await dloader.get_entity("banana")
    assert entity is None, entity
    entity = await dloader.get_entity(DAIMLER)
    assert entity is not None, entity
    assert "Daimler" in entity.caption, entity.caption
    assert len(entity.datasets) == 1
    for dataset in entity.datasets:
        assert "donations" in repr(dataset), dataset

    adjacent = [p async for p in dloader.get_adjacent(entity)]
    assert len(adjacent) == 10, len(adjacent)
    schemata = [e.schema for (_, e) in adjacent]
    assert model.get("Payment") in schemata, set(schemata)
    assert model.get("Address") in schemata, set(schemata)
    assert model.get("Company") not in schemata, set(schemata)
