from typing import Any, Dict, Generator
from abc import ABC, abstractmethod

from nomenklatura.entity import CE
from nomenklatura.dataset import DS, Dataset
from nomenklatura.cache import Cache


EnricherConfig = Dict[str, Any]


class Enricher(ABC):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        self.dataset = dataset
        self.cache = cache
        self.cache_days = int(config.pop("cache_days", 90))
        self.config = config

    @abstractmethod
    def match(self, entity: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def expand(self, entity: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    def close(self) -> None:
        self.cache.close()
