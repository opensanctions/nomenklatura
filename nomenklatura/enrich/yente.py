import json
from typing import Generator
from requests import Session
from followthemoney import model

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig


class YenteEnricher(Enricher):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
        self._endpoint = config.pop("endpoint")
        self._token = config.pop("token", "nomenklatura")
        self._session = Session()
        self._session.headers["Authorization"] = f"Bearer {self._token}"

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.matchable:
            return
        cache_key = f"{self._endpoint}:{entity.id}"
        response = self.cache.get_json(cache_key, max_age=self.cache_days)
        if response is None:
            data = {"queries": {"entity": entity.to_dict()}}
            resp = self._session.post(self._endpoint, json=data)
            response = resp.json().get("responses", {}).get("entity", {})
            self.cache.set_json(cache_key, response)
        for result in response.get("results", []):
            match = type(entity).from_dict(model, result, cleaned=False)
            yield match

    def expand(self, entity: CE) -> Generator[CE, None, None]:
        pass

    def close(self) -> None:
        super().close()
        self._session.close()
