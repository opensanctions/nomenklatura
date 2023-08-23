import json
import yaml
import pytest
from pathlib import Path
from tempfile import mkdtemp

from nomenklatura import settings
from nomenklatura.store import load_entity_file_store, SimpleMemoryStore
from nomenklatura.dataset import Dataset
from nomenklatura.index import Index

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")
WORK_PATH = mkdtemp()
settings.DB_URL = f"sqlite:///{WORK_PATH}/nk.sqlite3"


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


@pytest.fixture(scope="module")
def dstore(donations_path) -> SimpleMemoryStore:
    return load_entity_file_store(donations_path)


@pytest.fixture(scope="module")
def test_dataset() -> Dataset:
    return Dataset.make({"name": "test_dataset", "title": "Test Dataset"})


@pytest.fixture(scope="module")
def dindex(dstore: SimpleMemoryStore):
    index = Index(dstore.default_view())
    index.build()
    return index
