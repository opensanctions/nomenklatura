import json
import pytest
from pathlib import Path
from tempfile import mkdtemp
from sqlalchemy import create_engine

from nomenklatura.loader import FileLoader
from nomenklatura.index import Index

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")
DB_PATH = Path(mkdtemp()) / "test.sqlite3"


@pytest.fixture(scope="module")
def donations_path():
    return FIXTURES_PATH.joinpath("donations.ijson")


@pytest.fixture(scope="module")
def donations_json(donations_path):
    data = []
    with open(donations_path, "r") as fh:
        for line in fh.readlines():
            data.append(json.loads(line))
    return data


@pytest.fixture(scope="module")
def dloader(donations_path):
    return FileLoader(donations_path)


@pytest.fixture(scope="module")
def dindex(dloader):
    index = Index(dloader)
    index.build()
    return index


@pytest.fixture(scope="function")
def engine():
    return create_engine("sqlite:///:memory:")
    # return create_engine("sqlite:///%s" % DB_PATH.resolve().as_posix())
