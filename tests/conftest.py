import json
import shutil
from sqlalchemy import MetaData
import yaml
import pytest
from pathlib import Path
from tempfile import mkdtemp

from nomenklatura import settings
from nomenklatura.index.tantivy_index import TantivyIndex
from nomenklatura.store import load_entity_file_store, SimpleMemoryStore
from nomenklatura.kv import get_redis
from nomenklatura.db import get_engine, get_metadata
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.resolver import Resolver
from nomenklatura.index import Index

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")
settings.TESTING = True


@pytest.fixture(autouse=True)
def wrap_test():
    if not settings.DB_URL:
        settings.DB_URL = "sqlite:///:memory:"
    yield
    # Dispose of connections to let open transactions for resources not
    # managed by the setup/teardown abort.
    get_engine().dispose()
    get_engine.cache_clear()
    get_redis.cache_clear()
    get_metadata.cache_clear()


@pytest.fixture(scope="module")
def catalog_path():
    return FIXTURES_PATH.joinpath("catalog.yml")


@pytest.fixture(scope="module")
def catalog_data(catalog_path):
    with open(catalog_path, "r") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def donations_path() -> Path:
    return FIXTURES_PATH.joinpath("donations.ijson")


@pytest.fixture(scope="module")
def donations_json(donations_path):
    data = []
    with open(donations_path, "r") as fh:
        for line in fh.readlines():
            data.append(json.loads(line))
    return data


@pytest.fixture(scope="function")
def resolver():
    resolver = Resolver[CompositeEntity].make_default()
    yield resolver
    resolver.rollback(force=True)
    resolver._table.drop(resolver._engine)


@pytest.fixture(scope="function")
def other_table_resolver():
    engine = get_engine()
    meta = MetaData()
    resolver = Resolver(engine, meta, create=True, table_name="another_table")
    yield resolver
    resolver.rollback(force=True)
    resolver._table.drop(engine)


@pytest.fixture(scope="function")
def dstore(donations_path, resolver) -> SimpleMemoryStore:
    resolver.begin()
    return load_entity_file_store(donations_path, resolver)


@pytest.fixture(scope="module")
def test_dataset() -> Dataset:
    return Dataset.make({"name": "test_dataset", "title": "Test Dataset"})


@pytest.fixture(scope="function")
def index_path():
    index_path = Path(mkdtemp()) / "index-dir"
    yield index_path
    shutil.rmtree(index_path, ignore_errors=True)


@pytest.fixture(scope="function")
def dindex(index_path: Path, dstore: SimpleMemoryStore):
    index = Index(dstore.default_view(), index_path)
    index.build()
    return index


@pytest.fixture(scope="function")
def tantivy_index(index_path: Path, dstore: SimpleMemoryStore):
    index = TantivyIndex(dstore.default_view(), index_path)
    index.build()
    yield index
