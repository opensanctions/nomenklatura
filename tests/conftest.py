import json
import shutil
from sqlalchemy import MetaData
import yaml
import pytest
from pathlib import Path
from tempfile import mkdtemp
from normality import slugify_text
from followthemoney import Dataset, StatementEntity as Entity

from nomenklatura import settings
from nomenklatura.store import load_entity_file_store, SimpleMemoryStore
from nomenklatura.kv import get_redis
from nomenklatura.db import get_engine, get_metadata
from nomenklatura.resolver import Resolver
from nomenklatura.index import Index
from nomenklatura.cache import Cache

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")
settings.TESTING = True


@pytest.fixture(autouse=True)
def wrap_test():
    if settings.DB_URL.startswith("sqlite"):
        settings.DB_URL = "sqlite:///:memory:"
    yield
    # Dispose of connections to let open transactions for resources not
    # managed by the setup/teardown abort.
    engine = get_engine()
    meta = get_metadata()
    meta.drop_all(bind=engine)
    engine.dispose()
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
    resolver = Resolver[Entity].make_default()
    yield resolver
    resolver.rollback()
    resolver._table.drop(resolver._engine, checkfirst=True)


@pytest.fixture(scope="function")
def other_table_resolver():
    engine = get_engine()
    meta = MetaData()
    resolver = Resolver(engine, meta, create=True, table_name="another_table")
    yield resolver
    resolver.rollback()
    resolver._table.drop(engine)


@pytest.fixture(scope="function")
def dstore(donations_path, resolver) -> SimpleMemoryStore:
    resolver.begin()
    return load_entity_file_store(donations_path, resolver)


@pytest.fixture(scope="module")
def test_dataset() -> Dataset:
    return Dataset.make({"name": "test_dataset", "title": "Test Dataset"})


@pytest.fixture(scope="module")
def test_cache(test_dataset: Dataset) -> Cache:
    engine = get_engine(settings.DB_URL)
    metadata = MetaData()
    return Cache(engine, metadata, test_dataset, create=True)


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


def wd_read_response(request, context):
    """Read a local file if it exists, otherwise download it. This is not
    so much a mocker as a test disk cache."""
    file_name = slugify_text(request.url.split("/w/")[-1], sep="_")
    assert file_name is not None, "Invalid Wikidata URL: %s" % request.url
    path = FIXTURES_PATH / f"wikidata/{file_name}.json"
    if not path.exists():
        import urllib.request

        data = json.load(urllib.request.urlopen(request.url))
        for _, value in data["entities"].items():
            value.pop("sitelinks", None)
            for sect in ["labels", "aliases", "descriptions"]:
                # labels = value.get("labels", {})
                for lang in list(value.get(sect, {}).keys()):
                    if lang != "en":
                        del value[sect][lang]
        with open(path, "w") as fh:
            json.dump(data, fh)
    with open(path, "r") as fh:
        return json.load(fh)
