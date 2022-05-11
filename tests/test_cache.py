from pathlib import Path
from tempfile import mkdtemp

from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset

Cache.CACHE_PATH = Path(mkdtemp()) / "test.sqlite3"


def test_cache():
    ds = Dataset("test", "Test Case")
    cache = Cache.make_default(ds)
    res = cache.get("name")
    assert res is None, res
    assert not cache.has("name")

    cache.set("name", "TestCase")
    res = cache.get("name")
    assert res is not None, res
    assert res == "TestCase", res
    assert cache.has("name")

    res = cache.get("name", max_age=5)
    assert res == "TestCase", res

    cache.clear()
    res = cache.get("name")
    assert res is None, res

    cache.close()


def test_preload_cache():
    ds = Dataset("test", "Test Case")
    cache = Cache.make_default(ds)
    res = cache.get("name")
    cache.set("name", "TestCase")
    assert len(cache._preload) == 0, cache._preload
    cache.preload(like="foo%")
    assert len(cache._preload) == 0, cache._preload
    cache.preload(like="na%")
    assert len(cache._preload) == 1, cache._preload

    res = cache.get("name")
    assert res is not None, res
    assert res == "TestCase", res
    assert cache.has("name")

    res = cache.get("name", max_age=5)
    assert res == "TestCase", res
