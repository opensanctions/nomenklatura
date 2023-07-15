import orjson
from pathlib import Path
from typing import Optional

from nomenklatura.store.base import Store, Writer, View
from nomenklatura.store.memory import MemoryStore
from nomenklatura.resolver import Resolver
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity

SimpleMemoryStore = MemoryStore[Dataset, CompositeEntity]

__all__ = [
    "Store",
    "Writer",
    "View",
    "MemoryStore",
    "SimpleMemoryStore",
    "load_entity_file_store",
]


def load_entity_file_store(
    path: Path,
    resolver: Optional[Resolver[CompositeEntity]] = None,
    dataset: Optional[Dataset] = None,
    cleaned: bool = True,
) -> SimpleMemoryStore:
    """Create a simple in-memory store by reading FtM entities from a file path."""
    if resolver is None:
        resolver = Resolver[CompositeEntity]()
    if dataset is None:
        dataset = Dataset.make({"name": path.stem, "title": path.stem})
    store = MemoryStore(dataset, resolver)
    with store.writer() as writer:
        with open(path, "rb") as fh:
            while line := fh.readline():
                data = orjson.loads(line)
                proxy = CompositeEntity.from_data(dataset, data, cleaned=cleaned)
                writer.add_entity(proxy)
    return store
