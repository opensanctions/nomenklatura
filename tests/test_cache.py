from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset


def test_cache(engine):
    ds = Dataset("test", "Test Case")
    cache = Cache.make_default(ds, engine=engine)
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

    cache.set("banana", "TestCase")
    cache.delete("banana")
    assert not cache.has("banana")

    cache.close()


def test_cache_utils(engine):
    ds = Dataset("test", "Test Case")
    cache = Cache.make_default(ds, engine=engine)
    assert "memory" in repr(cache)
    assert hash(cache) != 0


def test_preload_cache(engine):
    ds = Dataset("test", "Test Case")
    cache = Cache.make_default(ds, engine=engine)
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
