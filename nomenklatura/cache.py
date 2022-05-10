import os
import shelve
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional, Union
from abc import ABC, abstractmethod

from nomenklatura.dataset import DS

Value = Union[str, None]


@dataclass
class CacheValue:
    value: Optional[str]
    timestamp: datetime


class Cache(ABC):
    @abstractmethod
    def set(self, dataset: DS, key: str, value: Value) -> None:
        pass

    @abstractmethod
    def get(self, dataset: DS, key: str) -> Optional[CacheValue]:
        pass

    def has(self, dataset: DS, key: str) -> bool:
        return self.get(dataset, key) is not None

    def close(self) -> None:
        pass


class FileCache(Cache):
    CACHE_PATH = os.environ.get("NOMENKLATURA_CACHE_PATH", ".nk_cache")

    def __init__(self):
        self.path = Path(self.CACHE_PATH).resolve()
        self._files: Dict[str, shelve.Shelf] = {}

    def _get_db(self, dataset: DS) -> shelve.Shelf:
        self.path.mkdir(exist_ok=True, parents=True)
        if dataset.name not in self._files:
            ds_path = self.path / f"{dataset.name}.cache"
            self._files[dataset.name] = shelve.open(ds_path.as_posix(), "c")
        return self._files[dataset.name]

    def set(self, dataset: DS, key: str, value: Value) -> None:
        db = self._get_db(dataset)
        ts = datetime.utcnow().timestamp()
        db[key] = dict(v=value, ts=ts)

    def get(self, dataset: DS, key: str) -> Optional[CacheValue]:
        db = self._get_db(dataset)
        data = db.get(key)
        if data is None:
            return None
        print(data)
        ts = datetime.fromtimestamp(data["ts"])
        return CacheValue(data["v"], ts)

    def close(self) -> None:
        for db in self._files.values():
            db.close()
