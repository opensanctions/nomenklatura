from pathlib import Path

import orjson
from followthemoney import Dataset, StatementEntity
from normality import slugify

from nomenklatura.resolver import Resolver
from nomenklatura.store.base import Store, View, Writer
from nomenklatura.store.memory import MemoryStore
from nomenklatura.store.sql import SQLStore

SimpleMemoryStore = MemoryStore[Dataset, StatementEntity]

__all__ = [
    "MemoryStore",
    "SQLStore",
    "SimpleMemoryStore",
    "Store",
    "View",
    "Writer",
    "load_entity_file_store",
]


def load_entity_file_store(
    path: Path,
    resolver: Resolver[StatementEntity],
    cleaned: bool = True,
) -> SimpleMemoryStore:
    """Create a simple in-memory store by reading FtM entities from a file path."""
    name = slugify(path.stem, sep="_") or Dataset.UNDEFINED
    dataset = Dataset.make({"name": name, "title": path.name})
    store = MemoryStore(dataset, resolver)
    with store.writer() as writer, open(path, "rb") as fh:
        while line := fh.readline():
            data = orjson.loads(line)
            proxy = StatementEntity.from_data(dataset, data, cleaned=cleaned)
            for ds in proxy.datasets:
                if ds not in dataset.dataset_names:
                    discovered = Dataset.make({"name": ds})
                    dataset.children.add(discovered)
            writer.add_entity(proxy)
    return store
