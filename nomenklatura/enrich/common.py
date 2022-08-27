import os
import json
from banal import as_bool
from typing import Union, Any, Dict, Optional, Generator
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
        self.config = config
        self.cache_days = int(config.pop("cache_days", 90))
        self.schemata = config.pop("schemata", [])
        self._session: Optional[Session] = None

    def get_config_expand(
        self, name: str, default: Optional[str] = None
    ) -> Optional[str]:
        value = self.config.get(name, default)
        if value is None:
            return None
        return str(os.path.expandvars(value))

    def get_config_int(self, name: str, default: Union[int, str]) -> int:
        return int(self.config.get(name, default))

    def get_config_bool(self, name: str, default: Union[bool, str] = False) -> int:
        return as_bool(self.config.get(name, default))

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session()
            self._session.headers["User-Agent"] = f"nomenklatura/{__version__}"
        return self._session

    def http_get_cached(
        self,
        url: str,
        params: ParamsType = None,
        hidden: ParamsType = None,
        cache_days: Optional[int] = None,
    ) -> str:
        url = normalize_url(url, params=params)
        cache_days_ = cache_days or self.cache_days
        response = self.cache.get(url, max_age=cache_days_)
        if response is None:
            hidden_url = normalize_url(url, params=hidden)
            resp = self.session.get(hidden_url)
            resp.raise_for_status()
            response = resp.text
            self.cache.set(url, response)
        return response

    def http_remove_cache(self, url: str, params: ParamsType = None) -> None:
        url = normalize_url(url, params=params)
        self.cache.delete(url)

    def http_get_json_cached(
        self,
        url: str,
        params: ParamsType = None,
        hidden: ParamsType = None,
        cache_days: Optional[int] = None,
    ) -> Any:
        res = self.http_get_cached(url, params, hidden=hidden, cache_days=cache_days)
        return json.loads(res)

    def load_entity(self, entity: CE, data: Dict[str, Any]) -> CE:
        proxy = type(entity).from_dict(model, data, cleaned=False)
        for prop in proxy.iterprops():
            if prop.stub:
                proxy.pop(prop)
        return proxy

    def make_entity(self, entity: CE, schema: str) -> CE:
        data = {"schema": schema}
        return type(entity).from_dict(model, data)

    def match_wrapped(self, entity: CE) -> Generator[CE, None, None]:
        if len(self.schemata) and entity.schema.name not in self.schemata:
            return
        yield from self.match(entity)

    def expand_wrapped(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        if len(self.schemata) and entity.schema.name not in self.schemata:
            return
        yield from self.expand(entity, match)

    @abstractmethod
    def match(self, entity: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        raise NotImplementedError()

    def close(self) -> None:
        self.cache.close()
        if self._session is not None:
            self._session.close()
