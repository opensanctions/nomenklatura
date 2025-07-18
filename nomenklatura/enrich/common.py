import os
import json
import logging
import traceback
from banal import as_bool
from typing import Union, Any, Dict, Optional, Generator, Generic
from abc import ABC, abstractmethod
from requests import Session
from requests.exceptions import RequestException, ChunkedEncodingError
from followthemoney import DS, registry
from followthemoney import StatementEntity, SE
from followthemoney.types.topic import TopicType
from rigour.urls import build_url, ParamsType

from nomenklatura import __version__
from nomenklatura.cache import Cache
from nomenklatura.util import HeadersType

EnricherConfig = Dict[str, Any]
log = logging.getLogger(__name__)


class EnrichmentException(Exception):
    pass


class EnrichmentAbort(Exception):
    pass


class BaseEnricher(Generic[DS]):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        self.dataset = dataset
        self.cache = cache
        self.config = config
        self.cache_days = int(config.pop("cache_days", 90))
        self._filter_schemata = config.pop("schemata", [])
        self._filter_topics = config.pop("topics", [])

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

    def _filter_entity(self, entity: StatementEntity) -> bool:
        """Check if the given entity should be filtered out. Filters
        can be applied by schema or by topic."""
        if len(self._filter_schemata):
            if entity.schema.name not in self._filter_schemata:
                return False
        _filter_topics = set(self._filter_topics)
        if "all" in _filter_topics:
            assert isinstance(registry.topic, TopicType)
            _filter_topics.update(registry.topic.names.keys())
        if len(_filter_topics):
            topics = set(entity.get_type_values(registry.topic))
            if not len(topics.intersection(_filter_topics)):
                return False
        return True


class Enricher(BaseEnricher[DS], ABC):
    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[Session] = None,
    ):
        super().__init__(dataset, cache, config)
        self._session: Optional[Session] = session

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
        url = build_url(url, params=params)
        cache_days_ = self.cache_days if cache_days is None else cache_days
        response = self.cache.get(url, max_age=cache_days_)
        if response is None:
            log.debug("HTTP GET: %s", url)
            hidden_url = build_url(url, params=hidden)
            try:
                resp = self.session.get(hidden_url)
                resp.raise_for_status()
            except RequestException as rex:
                if rex.response is not None and rex.response.status_code in (401, 403):
                    raise EnrichmentAbort("Authorization failure: %s" % url) from rex
                msg = "HTTP fetch failed [%s]: %s" % (url, rex)
                log.info(f"{msg}\n{traceback.format_exc()}")
                raise EnrichmentException(msg) from rex
            response = resp.text
            if cache_days_ > 0:
                self.cache.set(url, response)
        return response

    def http_remove_cache(self, url: str, params: ParamsType = None) -> None:
        url = build_url(url, params=params)
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
        json: Any = None,
        data: Any = None,
        headers: HeadersType = None,
        cache_days: Optional[int] = None,
        retry_chunked_encoding_error: int = 1,
    ) -> Any:
        cache_days_ = self.cache_days if cache_days is None else cache_days
        resp_data = self.cache.get_json(cache_key, max_age=cache_days_)
        if resp_data is None:
            try:
                resp = self.session.post(url, json=json, data=data, headers=headers)
                resp.raise_for_status()
            except ChunkedEncodingError as rex:
                # Due to https://github.com/urllib3/urllib3/issues/2751#issuecomment-2567630065,
                # urllib3's Retry strategy will not retry on chunked encoding errors.
                # Since urllib won't retry it, retry it here.
                # urllib does close the connection.
                if (
                    "Response ended prematurely" in str(rex)
                    and retry_chunked_encoding_error > 0
                ):
                    log.info("Retrying due to chunked encoding error: %s", rex)
                    return self.http_post_json_cached(
                        url,
                        cache_key,
                        json=json,
                        data=data,
                        headers=headers,
                        cache_days=cache_days,
                        retry_chunked_encoding_error=retry_chunked_encoding_error - 1,
                    )

                msg = "HTTP POST failed [%s]: %s" % (url, rex)
                raise EnrichmentException(msg) from rex
            except RequestException as rex:
                if rex.response is not None and rex.response.status_code in (401, 403):
                    raise EnrichmentAbort("Authorization failure: %s" % url) from rex

                msg = "HTTP POST failed [%s]: %s" % (url, rex)
                log.info(f"{msg}\n{traceback.format_exc()}")
                raise EnrichmentException(msg) from rex
            resp_data = resp.json()
            if cache_days_ > 0:
                self.cache.set_json(cache_key, resp_data)
        return resp_data

    def _make_data_entity(
        self, entity: SE, data: Dict[str, Any], cleaned: bool = True
    ) -> SE:
        """Create an entity which is of the same sub-type of SE as the given
        query entity."""
        return type(entity).from_data(self.dataset, data, cleaned=cleaned)

    def load_entity(self, entity: SE, data: Dict[str, Any]) -> SE:
        proxy = self._make_data_entity(entity, data, cleaned=False)
        for prop in proxy.iterprops():
            if prop.stub:
                proxy.pop(prop)
        return proxy

    def make_entity(self, entity: SE, schema: str) -> SE:
        """Create a new entity of the given schema."""
        return self._make_data_entity(entity, {"schema": schema})

    def match_wrapped(self, entity: SE) -> Generator[SE, None, None]:
        if not self._filter_entity(entity):
            return
        yield from self.match(entity)

    def expand_wrapped(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        if not self._filter_entity(entity):
            return
        yield from self.expand(entity, match)

    @abstractmethod
    def match(self, entity: SE) -> Generator[SE, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def expand(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        raise NotImplementedError()

    def close(self) -> None:
        self.cache.close()
        if self._session is not None:
            self._session.close()
