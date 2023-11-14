import os
import logging
from typing import Any, Generator, Dict, List
from urllib.parse import urljoin
from followthemoney.util import make_entity_id
from normality import slugify

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

    def make_company_id(self, name):
        return f"figi-co-{make_entity_id(name)}"

    def make_security_id(self, figi):
        return f"figi-id-{slugify(figi, sep='-')}"

    def search(self, query):
        body = {"query": query}
        next = None

        while True:
            if next is not None:
                body["start"] = next

            log.info(f"Searching {query}. Offset={next}")
            cache_key = f"{URL}:{query}:{next}"
            resp = self.http_post_json_cached(URL, cache_key, body)
            yield from resp["data"]

            next = resp.get("next", None)
            if next is None:
                break

    def match(self, entity: CE) -> Generator[CE, None, None]:
        for name in entity.get("name"):
            for match in self.search(name):
                other = self.make_entity(entity, "Company")
                name = match.get("name", None)
                if name is None:
                    continue
                other.id = self.make_company_id(name)
                other.add("name", name)
                yield other

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        yield match

        name = match.get("name")[0]
        for item in self.search(name):
            if item["name"] != name:
                continue

            security = self.make_entity(match, "Security")
            security.id = self.make_security_id(item["figi"])
            security.add("name", item["figi"])
            security.add("issuer", match)
            security.add("ticker", item["ticker"])
            security.add("type", item["securityType"])
            security.add("notes", f'exchange {item["exchCode"]}')

            yield security
