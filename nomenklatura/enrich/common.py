from typing import Any, Dict, Optional, Generator
from abc import ABC, abstractmethod
from requests import Session
from followthemoney import model

from nomenklatura import __version__
from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.util import ParamsType, normalize_url

EnricherConfig = Dict[str, Any]


class Enricher(ABC):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        self.dataset = dataset
        self.cache = cache
        self.cache_days = int(config.pop("cache_days", 90))
        self.config = config
        self._session: Optional[Session] = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session()
            self._session.headers["User-Agent"] = f"nomenklatura/{__version__}"
        return self._session

    def http_get_cached(self, url: str, params: ParamsType = None) -> str:
        url = normalize_url(url, params=params)
        response = self.cache.get(url, max_age=self.cache_days)
        if response is None:
            resp = self.session.get(url)
            resp.raise_for_status()
            response = resp.text
            self.cache.set(url, response)
        return response

    def load_entity(self, entity: CE, data: Dict[str, Any]) -> CE:
        return type(entity).from_dict(model, data, cleaned=False)

    def make_entity(self, entity: CE, schema: str) -> CE:
        data = {"schema": schema}
        return type(entity).from_dict(model, data)

    @abstractmethod
    def match(self, entity: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def expand(self, entity: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    def close(self) -> None:
        self.cache.close()
        if self._session is not None:
            self._session.close()
