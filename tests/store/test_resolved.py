import pytest
import orjson
import fakeredis
from pathlib import Path
from followthemoney import model
from datetime import datetime

from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.store.memory import MemoryStore
from nomenklatura.store.resolved import ResolvedStore
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.util import datetime_iso

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


def test_store_basics(test_dataset: Dataset):
    redis = fakeredis.FakeStrictRedis(version=6, decode_responses=False)
    resolver = Resolver[CompositeEntity]()
    store = ResolvedStore(test_dataset, resolver, db=redis)
    entity = CompositeEntity.from_data(test_dataset, PERSON)
    entity_ext = CompositeEntity.from_data(test_dataset, PERSON_EXT)
    assert len(list(store.view(test_dataset).entities())) == 0
    writer = store.writer()
    ts = datetime_iso(datetime.now())
    for stmt in entity.statements:
        stmt.first_seen = ts
        stmt.last_seen = ts
    writer.add_entity(entity)
    writer.flush()
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 1
    writer.add_entity(entity_ext)
    writer.flush()
    assert len(list(store.view(test_dataset).entities())) == 2

    merged_id = resolver.decide(
        "john-doe",
        "john-doe-2",
        judgement=Judgement.POSITIVE,
        user="test",
    )
    with pytest.raises(NotImplementedError):
        store.update(merged_id)


def test_graph_query(donations_path: Path, test_dataset: Dataset):
    redis = fakeredis.FakeStrictRedis(version=6, decode_responses=False)
    resolver = Resolver[CompositeEntity]()
    store = ResolvedStore(test_dataset, resolver, db=redis)
    assert len(list(store.view(test_dataset).entities())) == 0
    with store.writer() as writer:
        with open(donations_path, "rb") as fh:
            while line := fh.readline():
                data = orjson.loads(line)
                proxy = CompositeEntity.from_data(test_dataset, data)
                writer.add_entity(proxy)

    assert len(list(store.view(test_dataset).entities())) == 474

    view = store.default_view()
    entity = view.get_entity("banana")
    assert entity is None, entity
    assert not view.has_entity("banana")
    entity = view.get_entity(DAIMLER)
    assert entity is not None, entity
    assert view.has_entity(DAIMLER)
    assert "Daimler" in entity.caption, entity.caption
    assert len(entity.datasets) == 1
    ds = entity.datasets.pop()
    assert test_dataset.name in ds, ds

    adjacent = list(view.get_adjacent(entity))
    assert len(adjacent) == 10, len(adjacent)
    schemata = [e.schema for (_, e) in adjacent]
    assert model.get("Payment") in schemata, set(schemata)
    assert model.get("Address") in schemata, set(schemata)
    assert model.get("Company") not in schemata, set(schemata)

    ext_entity = CompositeEntity.from_data(test_dataset, PERSON)
    with store.writer() as writer:
        writer.add_entity(ext_entity)
        with pytest.raises(NotImplementedError):
            for stmt in entity.statements:
                writer.add_statement(stmt)

    view = store.view(test_dataset)
    ret_entity = view.get_entity("john-doe")
    assert ret_entity is not None, ret_entity
    assert len(list(ret_entity.statements)) == len(list(ext_entity.statements))
    assert view.has_entity("john-doe")
    assert not view.has_entity("john-doe-333")


def test_custom_functions(donations_path: Path, test_dataset: Dataset):
    redis = fakeredis.FakeStrictRedis(version=6, decode_responses=False)
    resolver = Resolver[CompositeEntity]()
    prefix = "test123"
    mem_store = MemoryStore(test_dataset, resolver)
    store = ResolvedStore(test_dataset, resolver, prefix=prefix, db=redis)
    with mem_store.writer() as writer:
        with open(donations_path, "rb") as fh:
            while line := fh.readline():
                data = orjson.loads(line)
                proxy = CompositeEntity.from_data(test_dataset, data)
                writer.add_entity(proxy)

    assert len(list(mem_store.view(test_dataset).entities())) == 474
    assert len(list(store.view(test_dataset).entities())) == 0
    store.derive(mem_store)
    assert len(list(store.view(test_dataset).entities())) == 474
    store.drop()
    assert len(list(store.view(test_dataset).entities())) == 0
