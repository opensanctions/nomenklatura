import os
import uuid
import logging
from banal import is_mapping, ensure_list, hash_data
from typing import Any, Dict, cast, Generator, Optional
from urllib.parse import urljoin
from functools import cached_property
from followthemoney.exc import InvalidData
from followthemoney.namespace import Namespace

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.util import normalize_url

log = logging.getLogger(__name__)


class AlephEnricher(Enricher):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
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

    @cached_property
    def collection_id(self) -> Optional[str]:
        if self._collection is None:
            return None
        url = urljoin(self._base_url, "collections")
        url = normalize_url(url, {"filter:foreign_id": self._collection})
        res = self.session.get(url)
        res.raise_for_status()
        response = res.json()
        for result in response.get("results", []):
            return cast(str, result["id"])
        return None

    def load_aleph_entity(self, entity: CE, data: Dict[str, Any]) -> Optional[CE]:
        data["referents"] = [data["id"]]
        try:
            proxy = super().load_entity(entity, data)
        except InvalidData:
            log.warning("Server model mismatch: %s" % data.get("schema"))
            return None
        links = data.get("links", {})
        proxy.add("alephUrl", links.get("self"), quiet=True, cleaned=True)
        collection = data.get("collection", {})
        proxy.add("publisher", collection.get("label"), quiet=True, cleaned=True)
        # clinks = collection.get("links", {})
        # entity.add("publisherUrl", clinks.get("ui"), quiet=True, cleaned=True)
        return proxy

    def convert_nested(
        self, entity: CE, data: Dict[str, Any]
    ) -> Generator[CE, None, None]:
        proxy = self.load_aleph_entity(entity, data)
        if proxy is not None:
            if self._ns is not None:
                entity = self._ns.apply(entity)
            yield proxy
        properties = data.get("properties", {})
        for prop, values in properties.items():
            for value in ensure_list(values):
                if is_mapping(value):
                    proxy = self.load_aleph_entity(entity, value)
                    if proxy is not None:
                        yield proxy

    # def enrich_entity(self, entity):
    #     url = self.api._make_url("match")
    #     for page in range(10):
    #         data = self.post_match(url, entity)
    #         for res in data.get("results", []):
    #             proxy = self.convert_entity(res)
    #             yield self.make_match(entity, proxy)

    #         url = data.get("next")
    #         if url is None:
    #             break

    # def expand_entity(self, entity):
    #     for url in entity.get("alephUrl", quiet=True):
    #         data = self.get_api(url)
    #         yield from self.convert_nested(data)

    #         _, entity_id = url.rsplit("/", 1)
    #         filters = (("entities", entity_id),)
    #         search_api = self.api._make_url("entities", filters=filters)
    #         while True:
    #             res = self.get_api(search_api)
    #             for data in ensure_list(res.get("results")):
    #                 yield from self.convert_nested(data)

    #             search_api = res.get("next")
    #             if search_api is None:
    #                 break

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.matchable:
            return
        url = urljoin(self._base_url, f"match")
        if self.collection_id is not None:
            url = normalize_url(url, {"collection_ids": self.collection_id})
        query = {
            "schema": entity.schema.name,
            "properties": entity.properties,
        }
        cache_id = entity.id or hash_data(query)
        cache_key = f"{url}:{cache_id}"
        response = self.cache.get_json(cache_key, max_age=self.cache_days)
        if response is None:
            resp = self.session.post(url, json=query)
            resp.raise_for_status()
            response = resp.json()
            self.cache.set_json(cache_key, response)
        for result in response.get("results", []):
            proxy = self.load_aleph_entity(entity, result)
            if proxy is not None:
                if self._ns is not None:
                    entity = self._ns.apply(entity)
                yield proxy

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        url = urljoin(self._base_url, f"entities/{match.id}")
        for aleph_url in match.get("alephUrl", quiet=True):
            if aleph_url.startswith(self._base_url):
                url = aleph_url.replace("/entities/", "/api/2/entities/")
        response = self.http_get_json_cached(url)
        yield from self.convert_nested(match, response)
