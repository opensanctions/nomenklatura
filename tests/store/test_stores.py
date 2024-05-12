"""
Test if the different store implementations all behave the same.
"""

from pathlib import Path
from typing import Any, Dict, List

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.resolver import Resolver
from nomenklatura.store import SimpleMemoryStore, SQLStore, Store
from nomenklatura.store.level import LevelDBStore


def _run_store_test(
    store: Store[Dataset, CompositeEntity],
    dataset: Dataset,
    donations_json: List[Dict[str, Any]],
):
    entity_id = "4e0bd810e1fcb49990a2b31709b6140c4c9139c5"
    view = store.default_view()
    assert not view.has_entity(entity_id)

    with store.writer() as bulk:
        for data in donations_json:
            proxy = CompositeEntity.from_data(dataset, data)
            bulk.add_entity(proxy)

    view = store.default_view()
    proxies = [e for e in view.entities()]
    assert len(proxies) == len(donations_json)

    entity = view.get_entity(entity_id)
    assert entity is not None
    assert entity.id is not None
    assert entity.caption == "Tchibo Holding AG"
    assert view.has_entity(entity.id)

    tested = False
    for prop, value in entity.itervalues():
        if prop.type.name == "entity":
            for iprop, ientity in view.get_inverted(value):
                assert iprop.reverse == prop
                assert ientity == entity
                tested = True
    assert tested

    adjacent = list(view.get_adjacent(entity))
    assert len(adjacent) == 2

    writer = store.writer()
    stmts = writer.pop(entity.id)
    writer.flush()
    assert len(stmts) == len(list(entity.statements))
    assert view.get_entity(entity.id) is None

    # upsert
    with store.writer() as bulk:
        for data in donations_json:
            proxy = CompositeEntity.from_data(dataset, data)
            bulk.add_entity(proxy)

    proxies = [e for e in view.entities()]
    assert len(proxies) == len(donations_json)
    entity = view.get_entity(entity.id)
    assert entity is not None
    assert entity.caption == "Tchibo Holding AG"
    return True


def test_store_sql(
    tmp_path: Path, test_dataset: Dataset, donations_json: List[Dict[str, Any]]
):
    resolver = Resolver[CompositeEntity]()
    uri = f"sqlite:///{tmp_path / 'test.db'}"
    store = SQLStore(dataset=test_dataset, linker=resolver, uri=uri)
    assert str(store.engine.url) == uri
    assert _run_store_test(store, test_dataset, donations_json)


def test_store_memory(test_dataset: Dataset, donations_json: List[Dict[str, Any]]):
    resolver = Resolver[CompositeEntity]()
    store = SimpleMemoryStore(dataset=test_dataset, linker=resolver)
    assert _run_store_test(store, test_dataset, donations_json)


def test_store_level(
    tmp_path: Path, test_dataset: Dataset, donations_json: List[Dict[str, Any]]
):
    resolver = Resolver[CompositeEntity]()
    path = tmp_path / "level.db"
    store = LevelDBStore(dataset=test_dataset, linker=resolver, path=path)
    assert _run_store_test(store, test_dataset, donations_json)
