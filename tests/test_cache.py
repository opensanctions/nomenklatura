from pathlib import Path
from tempfile import mkdtemp

from nomenklatura.cache import FileCache
from nomenklatura.dataset import Dataset

FileCache.CACHE_PATH = Path(mkdtemp())


def test_file_cache():
    ds = Dataset("test", "Test Case")
    cache = FileCache()
    res = cache.get(ds, "name")
    assert res is None, res
    assert not cache.has(ds, "name")

    cache.set(ds, "name", "TestCase")
    res = cache.get(ds, "name")
    assert res.value == "TestCase", res
    assert cache.has(ds, "name")
