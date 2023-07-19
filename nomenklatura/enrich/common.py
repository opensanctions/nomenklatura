import os
import json
import logging
from banal import as_bool
from typing import Union, Any, Dict, Optional, Generator
from abc import ABC, abstractmethod
from requests import Session
from requests.exceptions import RequestException

from nomenklatura import __version__
from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.util import ParamsType, normalize_url

EnricherConfig = Dict[str, Any]
log = logging.getLogger(__name__)


class EnrichmentException(Exception):
    pass


class EnrichmentAbort(Exception):
    pass


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
        cache_days_ = self.cache_days if cache_days is None else cache_days
        response = self.cache.get(url, max_age=cache_days_)
        if response is None:
            log.debug("HTTP GET: %s", url)
            hidden_url = normalize_url(url, params=hidden)
            try:
                resp = self.session.get(hidden_url)
                resp.raise_for_status()
            except RequestException as rex:
                if rex.response is not None and rex.response.status_code in (401, 403):
                    raise EnrichmentAbort("Authorization failure: %s" % url) from rex
                msg = "HTTP fetch failed [%s]: %s" % (url, rex)
                raise EnrichmentException(msg) from rex
            response = resp.text
            if cache_days_ > 0:
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

    def http_post_json_cached(
        self,
        url: str,
        cache_key: str,
        json: Any,
        cache_days: Optional[int] = None,
    ) -> Any:
        cache_days_ = self.cache_days if cache_days is None else cache_days
        resp_data = self.cache.get_json(cache_key, max_age=cache_days_)
        if resp_data is None:
            try:
                resp = self.session.post(url, json=json)
                resp.raise_for_status()
            except RequestException as rex:
                if rex.response is not None and rex.response.status_code in (401, 403):
                    raise EnrichmentAbort("Authorization failure: %s" % url) from rex
                msg = "HTTP POST failed [%s]: %s" % (url, rex)
                raise EnrichmentException(msg) from rex
            resp_data = resp.json()
            if cache_days_ > 0:
                self.cache.set_json(cache_key, resp_data)
        return resp_data

    def _make_data_entity(
        self, entity: CE, data: Dict[str, Any], cleaned: bool = True
    ) -> CE:
        return type(entity).from_data(self.dataset, data, cleaned=cleaned)

    def load_entity(self, entity: CE, data: Dict[str, Any]) -> CE:
        proxy = self._make_data_entity(entity, data, cleaned=False)
        for prop in proxy.iterprops():
            if prop.stub:
                proxy.pop(prop)
        return proxy

    def make_entity(self, entity: CE, schema: str) -> CE:
        return self._make_data_entity(entity, {"schema": schema})

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
