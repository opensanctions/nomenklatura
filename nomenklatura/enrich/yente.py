import logging
from typing import Any, Generator
from requests import Session
from urllib.parse import urljoin
from banal import ensure_list
from followthemoney.types import registry

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig

log = logging.getLogger(__name__)


class YenteEnricher(Enricher):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
        self._api = config.pop("api")
        self._dataset = config.pop("dataset", "default")
        self._token = config.pop("token", "nomenklatura")
        self._session = Session()
        self._session.headers["Authorization"] = f"Bearer {self._token}"

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.matchable:
            return
        url = urljoin(self._api, f"match/{self._dataset}")
        cache_key = f"{url}:{entity.id}"
        response = self.cache.get_json(cache_key, max_age=self.cache_days)
        if response is None:
            data = {"queries": {"entity": entity.to_dict()}}
            resp = self._session.post(url, json=data)
            response = resp.json().get("responses", {}).get("entity", {})
            self.cache.set_json(cache_key, response)
        for result in response.get("results", []):
            yield self.load_entity(entity, result)

    def _traverse_nested(self, entity: CE, response: Any) -> Generator[CE, None, None]:
        entity = self.load_entity(entity, response)
        yield entity
        for prop_name, values in response.get("properties", {}).items():
            prop = entity.schema.properties.get(prop_name)
            if prop is None or prop.type != registry.entity:
                continue
            for value in ensure_list(values):
                if isinstance(value, dict):
                    yield from self._traverse_nested(entity, value)

    def expand(self, entity: CE) -> Generator[CE, None, None]:
        url = urljoin(self._api, f"entities/{entity.id}?nested=true")
        response = self.cache.get_json(url, max_age=self.cache_days)
        if response is None:
            resp = self._session.get(url)
            if resp.status_code != 200:
                log.warning("Error: %s", resp.text)
                return
            response = resp.json()
            self.cache.set_json(url, response)
        yield from self._traverse_nested(entity, response)

    def close(self) -> None:
        super().close()
        self._session.close()
