import os
import uuid
import logging
from banal import is_mapping, ensure_list, hash_data
from typing import Any, Dict, cast, Generator, Optional
from urllib.parse import urljoin
from functools import cached_property
from followthemoney.exc import InvalidData
from followthemoney.namespace import Namespace
from followthemoney import DS, SE
from requests import Session
from rigour.urls import build_url

from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig

log = logging.getLogger(__name__)


class BrightQueryEnricher(Enricher[DS]):
    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[Session] = None,
    ):
        super().__init__(dataset, cache, config, session)
        self._host: str = os.environ.get("ALEPH_HOST", "https://aleph.occrp.org/")
        self._host = self.get_config_expand("host") or self._host
        self._base_url: str = urljoin(self._host, "/api/2/")
        self._collection: Optional[str] = self.get_config_expand("collection")
        self._ns: Optional[Namespace] = None
        if self.get_config_bool("strip_namespace"):
            self._ns = Namespace()
        self._api_key: Optional[str] = os.environ.get("ALEPH_API_KEY")
        self._api_key = self.get_config_expand("api_key") or self._api_key
        if self._api_key is not None:
            self.session.headers["Authorization"] = f"ApiKey {self._api_key}"
        self.session.headers["X-Aleph-Session"] = str(uuid.uuid4())

    def match(self, entity: SE) -> Generator[SE, None, None]:
        if not entity.schema.matchable:
            return
        url = urljoin(self._base_url, "match")
        if self.collection_id is not None:
            url = build_url(url, {"collection_ids": self.collection_id})
        query = {
            "schema": entity.schema.name,
            "properties": entity.properties,
        }
        cache_id = entity.id or hash_data(query)
        cache_key = f"{url}:{cache_id}"
        response = self.http_post_json_cached(url, cache_key, query)
        for result in response.get("results", []):
            proxy = self.load_aleph_entity(entity, result)
            if proxy is not None:
                if self._ns is not None:
                    entity = self._ns.apply(entity)
                yield proxy

    def expand(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        yield match
        # url = urljoin(self._base_url, f"entities/{match.id}")
        # for aleph_url in match.get("alephUrl", quiet=True):
        #     if aleph_url.startswith(self._base_url):
        #         url = aleph_url.replace("/entities/", "/api/2/entities/")
        # response = self.http_get_json_cached(url)
        # yield from self.convert_nested(match, response)
