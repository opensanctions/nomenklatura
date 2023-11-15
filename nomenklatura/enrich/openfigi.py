import os
import logging
from typing import Generator, Dict, Optional
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
        api_key_var = "${OPENFIGI_API_KEY}"
        self.api_key: Optional[str] = self.get_config_expand("api_key", api_key_var)
        if self.api_key == api_key_var:
            self.api_key = None
        if self.api_key is None:
            log.warning("PermID has no API token (%s)" % api_key_var)

        api_key = os.environ.get("OPENFIGI_API_KEY")
        if api_key is not None:
            self.session.headers["X-OPENFIGI-APIKEY"] = api_key

    def make_company_id(self, name: str) -> str:
        return f"figi-co-{make_entity_id(name)}"

    def make_security_id(self, figi: str) -> str:
        return f"figi-id-{slugify(figi, sep='-')}"

    def search(self, query: str) -> Generator[Dict[str, str], None, None]:
        body = {"query": query}
        next = None

        while True:
            if next is not None:
                body["start"] = next

            log.info(f"Searching {query}. Offset={next}")
            cache_key = f"{URL}:{query}:{next}"
            resp = self.http_post_json_cached(URL, cache_key, json=body)
            if "data" in resp:
                yield from resp["data"]

            next = resp.get("next", None)
            if next is None:
                break

    def match(self, entity: CE) -> Generator[CE, None, None]:
        for name in entity.get("name"):
            for match in self.search(name):
                match_name = match.get("name", None)
                if match_name is None:
                    continue
                other = self.make_entity(entity, "Company")
                other.id = self.make_company_id(match_name)
                other.add("name", match_name)
                yield other

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        name = match.get("name")[0]
        for item in self.search(name):

            # Only emit the securities which match the name of the positive match
            # to the company exactly. Skip everything else.
            if item["name"] != name:
                continue

            security = self.make_entity(match, "Security")
            security.id = self.make_security_id(item["figi"])
            security.add("name", item["figi"])
            security.add("issuer", match)
            security.add("ticker", item["ticker"])
            security.add("type", item["securityType"])
            if item["exchCode"] is not None:
                security.add("notes", f'exchange {item["exchCode"]}')
            security.add("description", item["securityDescription"])

            yield security
