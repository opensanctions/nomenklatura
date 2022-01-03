import json
import pytest
import asyncio
from pathlib import Path

from nomenklatura.loader import FileLoader
from nomenklatura.index import Index

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")


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
async def dloader(donations_path):
    return await FileLoader.from_file(donations_path)


@pytest.fixture(scope="module")
async def dindex(dloader):
    index = Index(dloader)
    await index.build()
    return index


@pytest.fixture(scope="module")
def event_loop(request):
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
