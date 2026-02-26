"""
Test if the different store implementations all behave the same.
"""

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity
from pytest import MonkeyPatch
from sqlalchemy import create_mock_engine

from nomenklatura import settings
from nomenklatura.db import SQLITE_MAX_VARS
from nomenklatura.resolver import Resolver
from nomenklatura.store import SimpleMemoryStore, SQLStore, Store
from nomenklatura.store.level import LevelDBStore
from nomenklatura.store.sql import SQLWriter


def _run_store_test(
    store: Store[Dataset, Entity],
    dataset: Dataset,
    donations_json: List[Dict[str, Any]],
):
    entity_id = "4e0bd810e1fcb49990a2b31709b6140c4c9139c5"
    view = store.default_view()
    assert not view.has_entity(entity_id)

    with store.writer() as bulk:
        for data in donations_json:
            proxy = Entity.from_data(dataset, data)
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
            proxy = Entity.from_data(dataset, data)
            bulk.add_entity(proxy)

    proxies = [e for e in view.entities()]
    assert len(proxies) == len(donations_json)
    entity = view.get_entity(entity.id)
    assert entity is not None
    assert entity.caption == "Tchibo Holding AG"
    return True


def test_store_sql(
    tmp_path: Path,
    test_dataset: Dataset,
    donations_json: List[Dict[str, Any]],
    resolver: Resolver[Entity],
):
    resolver.begin()
    uri = f"sqlite:///{tmp_path / 'test.db'}"
    store = SQLStore(dataset=test_dataset, linker=resolver, uri=uri)
    assert str(store.engine.url) == uri
    assert _run_store_test(store, test_dataset, donations_json)


def test_sql_writer_sqlite_batch_limit_cap(
    tmp_path: Path,
    test_dataset: Dataset,
    resolver: Resolver[Entity],
    monkeypatch: MonkeyPatch,
):
    resolver.begin()
    uri = f"sqlite:///{tmp_path / 'test.db'}"
    store = SQLStore(dataset=test_dataset, linker=resolver, uri=uri)
    monkeypatch.setattr(settings, "STATEMENT_BATCH", 10000)
    writer = store.writer()
    assert isinstance(writer, SQLWriter)
    assert writer.batch_limit == SQLITE_MAX_VARS // len(store.table.columns)


def test_sql_writer_sqlite_batch_limit_uses_setting_when_lower(
    tmp_path: Path,
    test_dataset: Dataset,
    resolver: Resolver[Entity],
    monkeypatch: MonkeyPatch,
):
    resolver.begin()
    uri = f"sqlite:///{tmp_path / 'test.db'}"
    store = SQLStore(dataset=test_dataset, linker=resolver, uri=uri)
    monkeypatch.setattr(settings, "STATEMENT_BATCH", 500)
    writer = store.writer()
    assert isinstance(writer, SQLWriter)
    assert writer.batch_limit == 500


def test_sql_writer_postgresql_no_batch_limit_cap(monkeypatch: MonkeyPatch):
    mock_store = MagicMock()
    mock_store.engine = create_mock_engine("postgresql:///", lambda *a, **kw: None)
    monkeypatch.setattr(settings, "STATEMENT_BATCH", 10000)
    writer = SQLWriter(mock_store)
    assert writer.batch_limit == 10000


def test_store_memory(
    test_dataset: Dataset,
    donations_json: List[Dict[str, Any]],
    resolver: Resolver[Entity],
):
    resolver.begin()
    store = SimpleMemoryStore(dataset=test_dataset, linker=resolver)
    assert _run_store_test(store, test_dataset, donations_json)


def test_store_level(
    tmp_path: Path,
    test_dataset: Dataset,
    donations_json: List[Dict[str, Any]],
    resolver: Resolver[Entity],
):
    resolver.begin()
    path = tmp_path / "level.db"
    store = LevelDBStore(dataset=test_dataset, linker=resolver, path=path)
    assert _run_store_test(store, test_dataset, donations_json)
