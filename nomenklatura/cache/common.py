import math
import json
import logging
from random import randint
from typing import Any, Optional, Generator
from datetime import timedelta

from nomenklatura.dataset import Dataset


log = logging.getLogger(__name__)


def randomize_cache(days: int) -> timedelta:
    min_cache = max(1, math.ceil(days * 0.7))
    max_cache = math.ceil(days * 1.3)
    return timedelta(days=randint(min_cache, max_cache))


class Cache(object):
    def set(self, key: str, value: Optional[str]) -> None:
        pass

    def set_json(self, key: str, value: Any) -> None:
        return self.set(key, json.dumps(value))

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[str]:
        raise NotImplementedError

    def get_json(self, key: str, max_age: Optional[int] = None) -> Optional[Any]:
        text = self.get(key, max_age=max_age)
        if text is None:
            return None
        return json.loads(text)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def all(self, like: Optional[str]) -> Generator[Optional[str], None, None]:
        raise NotImplementedError

    def preload(self, like: Optional[str] = None) -> None:
        pass

    def clear(self) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.flush()

    def __repr__(self) -> str:
        return f"<Cache({self._table!r})>"

    def __hash__(self) -> int:
        return hash((self.dataset.name, self._table.name))

    @classmethod
    def make_default(cls, dataset: Dataset) -> "Cache":
        raise NotImplementedError
