from pathlib import Path
from typing import Optional

import orjson

from followthemoney import Dataset, StatementEntity
from nomenklatura.resolver import Resolver
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.store.memory import MemoryStore
from nomenklatura.store.sql import SQLStore

SimpleMemoryStore = MemoryStore[Dataset, StatementEntity]

__all__ = [
    "Store",
    "Writer",
    "View",
    "MemoryStore",
    "SimpleMemoryStore",
    "SQLStore",
    "load_entity_file_store",
]


def load_entity_file_store(
    path: Path,
    resolver: Resolver[StatementEntity],
    dataset: Optional[Dataset] = None,
    cleaned: bool = True,
) -> SimpleMemoryStore:
    """Create a simple in-memory store by reading FtM entities from a file path."""
    if dataset is None:
        dataset = Dataset.make({"name": path.stem, "title": path.stem})
    store = MemoryStore(dataset, resolver)
    with store.writer() as writer:
        with open(path, "rb") as fh:
            while line := fh.readline():
                data = orjson.loads(line)
                proxy = StatementEntity.from_data(dataset, data, cleaned=cleaned)
                writer.add_entity(proxy)
    return store
