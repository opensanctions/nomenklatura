import os
import logging
from typing import Any, Generator, Dict, List
from urllib.parse import urljoin

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig

log = logging.getLogger(__name__)
URL = "https://api.openfigi.com/v3/search"


class OpenFIGIEnricher(Enricher):
    """Uses the `OpenFIGI` search API to look up FIGIs by company name."""

    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
        
        api_key = os.environ.get("OPENFIGI_API_KEY")
        self.session.headers["X-OPENFIGI-APIKEY"] = api_key

    def make_entity_id(self, name):
        return make_entity_id("name", name, )


    def match(self, entity: CE) -> Generator[CE, None, None]:
        for name in entity.get("name"):                        
            body = {"query": name}
            next = None

            while True:
                if next is not None:
                    body["start"] = next

                log.info(f"Searching {name}. Offset={next}")
                cache_key = f"{URL}:{name}:{next}"
                resp = self.http_post_json_cached(URL, cache_key, body)

                for match in resp.get("data"):
                    print(name, "->", match["name"])
                    other = self.make_entity(entity, "Company")
                    other.id = self.make_entity_id(match["name"])
                    other.add("name", match["name"])
                    yield other

                next = resp.get("next", None)
                if next is None:
                    break


    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
       pass 
