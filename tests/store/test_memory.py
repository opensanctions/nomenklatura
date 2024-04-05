from followthemoney import model

from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.store import MemoryStore, SimpleMemoryStore
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"

PERSON = {
    "id": "john-doe",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}

PERSON_EXT = {
    "id": "john-doe-2",
    "schema": "Person",
    "properties": {"birthPlace": ["North Texas"]},
}


def test_basic_store(test_dataset: Dataset):
    resolver = Resolver[CompositeEntity]()
    store = MemoryStore(test_dataset, resolver)
    entity = CompositeEntity.from_data(test_dataset, PERSON)
    entity_ext = CompositeEntity.from_data(test_dataset, PERSON_EXT)
    assert len(store.stmts) == 0
    writer = store.writer()
    writer.add_entity(entity)
    writer.flush()
    assert len(store.stmts) == 1
    assert len(list(store.view(test_dataset).entities())) == 1
    writer.add_entity(entity_ext)
    writer.flush()
    assert len(store.stmts) == 2
    assert len(list(store.view(test_dataset).entities())) == 2

    merged_id = resolver.decide(
        "john-doe",
        "john-doe-2",
        judgement=Judgement.POSITIVE,
        user="test",
    )
    store.update(merged_id)
    assert len(store.stmts) == 1
    assert len(list(store.view(test_dataset).entities())) == 1


def test_store_init(donations_json, dstore: SimpleMemoryStore):
    view = dstore.default_view()
    entities = [e for e in view.entities()]
    assert len(donations_json) == len(entities)


def test_get_entity(dstore: SimpleMemoryStore):
    view = dstore.default_view()
    entity = view.get_entity("banana")
    assert entity is None, entity
    entity = view.get_entity(DAIMLER)
    assert entity is not None, entity
    assert "Daimler" in entity.caption, entity.caption
    assert len(entity.datasets) == 1
    ds = entity.datasets.pop()
    assert "donations" in ds, ds

    adjacent = list(view.get_adjacent(entity))
    assert len(adjacent) == 10, len(adjacent)
    schemata = [e.schema for (_, e) in adjacent]
    assert model.get("Payment") in schemata, set(schemata)
    assert model.get("Address") in schemata, set(schemata)
    assert model.get("Company") not in schemata, set(schemata)


def test_has_entity(dstore: SimpleMemoryStore, test_dataset: Dataset):
    view = dstore.default_view()
    assert not view.has_entity("banana")
    assert view.has_entity(DAIMLER)

    assert not view.has_entity("john-doe-2")
    writer = dstore.writer()
    entity_ext = CompositeEntity.from_data(test_dataset, PERSON_EXT)
    writer.add_entity(entity_ext)
    writer.flush()
    assert view.has_entity("john-doe-2")
