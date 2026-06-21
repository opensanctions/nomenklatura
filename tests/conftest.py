import json
import shutil
from typing import Any, Callable, Dict, Generator, List
import yaml
import pytest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path
from tempfile import mkdtemp
from normality import slugify_text
from followthemoney import Dataset, StatementEntity as Entity

from nomenklatura import settings
from nomenklatura.store import load_entity_file_store, SimpleMemoryStore
from nomenklatura.kv import get_redis
from nomenklatura.db import close_db, get_engine, get_metadata, make_session, Session
from nomenklatura.resolver import Resolver
from nomenklatura.blocker.index import Index
from nomenklatura.cache import Cache

FIXTURES_PATH = Path(__file__).parent.joinpath("fixtures/")
FIXTURE_FETCH_HEADERS = {
    "User-Agent": "followthemoney.tech/nomenklatura (https://github.com/opensanctions/nomenklatura)",
    "Accept": "application/json",
}
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
    close_db()
    get_redis.cache_clear()


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
def donations_json(donations_path: Path) -> List[Dict[str, Any]]:
    data = []
    with open(donations_path, "r") as fh:
        for line in fh.readlines():
            data.append(json.loads(line))
    return data


@pytest.fixture(scope="function")
def resolver(db_session: Session) -> Resolver[Entity]:
    return Resolver[Entity](db_session, create=True)


@pytest.fixture(scope="function")
def other_table_resolver(db_session: Session) -> Resolver[Entity]:
    return Resolver(db_session, create=True, table_name="another_table")


@pytest.fixture(scope="function")
def dstore(donations_path: Path, resolver: Resolver[Entity]) -> SimpleMemoryStore:
    resolver.load_into_memory()
    return load_entity_file_store(donations_path, resolver)


@pytest.fixture(scope="module")
def test_dataset() -> Dataset:
    return Dataset.make({"name": "test_dataset", "title": "Test Dataset"})


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """One unit-of-work session per test, disposed on teardown.

    Mirrors the production ownership model (the test is the owner) and, more
    importantly, guarantees the connection is released — no test can leak an
    open transaction into the next.
    """
    session = make_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def test_cache(db_session: Session, test_dataset: Dataset) -> Cache:
    return Cache(db_session, test_dataset, create=True)


@pytest.fixture(scope="function")
def cache_factory(db_session: Session) -> Callable[[Dataset], Cache]:
    """Build a cache for an arbitrary dataset on the per-test session.

    Replaces the old ``Cache.make_default`` in tests that need a cache for a
    dataset other than ``test_dataset`` (wikidata, enrichers, ...).
    """
    return lambda dataset: Cache(db_session, dataset, create=True)


@pytest.fixture(scope="function")
def index_path() -> Generator[Path, None, None]:
    index_path = Path(mkdtemp()) / "index-dir"
    yield index_path
    shutil.rmtree(index_path, ignore_errors=True)


@pytest.fixture(scope="function")
def dindex(index_path: Path, dstore: SimpleMemoryStore) -> Generator[Index, None, None]:
    index = Index(dstore.default_view(), index_path)
    index.build()
    yield index
    index.close()


def wd_read_response(request, context):
    """Read a local file if it exists, otherwise download it. This is not
    so much a mocker as a test disk cache."""
    file_name = slugify_text(request.url.split("/w/")[-1], sep="_")
    assert file_name is not None, "Invalid Wikidata URL: %s" % request.url
    path = FIXTURES_PATH / f"wikidata/{file_name}.json"
    if not path.exists():
        try:
            req = Request(request.url, headers=FIXTURE_FETCH_HEADERS)
            data = json.load(urlopen(req))
        except HTTPError as exc:
            print("URL", request.url, "failed:", exc, exc.read())
            raise
        for _, value in data["entities"].items():
            for k in list(value.get("sitelinks", {}).keys()):
                if k not in ("enwiki", "ruwiki", "dewiki", "arwiki"):
                    value["sitelinks"].pop(k, None)
            for sect in ["labels", "aliases", "descriptions"]:
                # labels = value.get("labels", {})
                for lang in list(value.get(sect, {}).keys()):
                    if lang != "en":
                        del value[sect][lang]
        with open(path, "w") as fh:
            json.dump(data, fh)
    with open(path, "r") as fh:
        return json.load(fh)
