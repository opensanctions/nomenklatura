from nomenklatura.cache import Cache


def test_cache(test_cache: Cache):
    assert test_cache is not None
    # ds = Dataset.make({"name": "test", "title": "Test Case"})
    # cache = _make_cache(ds)
    res = test_cache.get("name")
    assert res is None, res
    assert not test_cache.has("name")

    test_cache.set("name", "TestCase")
    res = test_cache.get("name")
    assert res is not None, res
    assert res == "TestCase", res
    test_cache.flush()
    assert test_cache.has("name")

    res = test_cache.get("name", max_age=5)
    assert res == "TestCase", res

    test_cache.clear()
    res = test_cache.get("name")
    assert res is None, res

    test_cache.set("banana", "TestCase")
    test_cache.delete("banana")
    assert not test_cache.has("banana")

    test_cache.close()


def test_cache_utils(test_cache: Cache):
    assert hash(test_cache) != 0
    test_cache.close()


def test_preload_cache(test_cache: Cache):
    res = test_cache.get("name")
    test_cache.set("name", "TestCase")
    assert len(test_cache._preload) == 0, test_cache._preload
    test_cache.preload(like="foo%")
    assert len(test_cache._preload) == 0, test_cache._preload
    test_cache.preload(like="na%")
    assert len(test_cache._preload) == 1, test_cache._preload

    res = test_cache.get("name")
    assert res is not None, res
    assert res == "TestCase", res
    assert test_cache.has("name")

    res = test_cache.get("name", max_age=5)
    assert res == "TestCase", res
    test_cache.close()
