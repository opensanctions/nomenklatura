import os
import logging
from typing import Generator, Dict, Optional
from followthemoney.util import make_entity_id

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig

log = logging.getLogger(__name__)


class OpenFIGIEnricher(Enricher):
    """Uses the `OpenFIGI` search API to look up FIGIs by company name."""

    SEARCH_URL = "https://api.openfigi.com/v3/search"
    MAPPING_URL = "https://api.openfigi.com/v3/mapping"

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
        return f"figi-company-{make_entity_id(name)}"

    def make_security_id(self, figi: str) -> str:
        return f"figi-{figi}"

    def search(self, query: str) -> Generator[Dict[str, str], None, None]:
        body = {"query": query}
        next = None

        while True:
            if next is not None:
                body["start"] = next

            log.info(f"Searching {query!r}, offset={next}")
            cache_key = f"{self.SEARCH_URL}:{query}:{next}"
            resp = self.http_post_json_cached(self.SEARCH_URL, cache_key, json=body)
            if "data" in resp:
                yield from resp["data"]

            next = resp.get("next", None)
            if next is None:
                break

    def match_organization(self, entity: CE) -> Generator[CE, None, None]:
        for name in entity.get("name"):
            for match in self.search(name):
                match_name = match.get("name", None)
                if match_name is None:
                    continue
                other = self.make_entity(entity, "Company")
                other.id = self.make_company_id(match_name)
                other.add("name", match_name)
                other.add("topics", "corp.public")
                yield other

    def match_security(self, entity: CE) -> Generator[CE, None, None]:
        for isin in entity.get("isin"):
            cache_key = f"{self.MAPPING_URL}:ISIN:{isin}"
            query = [{"idType": "ID_ISIN", "idValue": isin}]
            resp = self.http_post_json_cached(self.MAPPING_URL, cache_key, json=query)
            for section in resp:
                for item in section.get("data", []):
                    figi = item["figi"]
                    if figi != item.get("compositeFIGI", figi):
                        continue
                    security = self.make_entity(entity, "Security")
                    # security.id = self.make_security_id(item["figi"])
                    security.id = entity.id
                    security.add("isin", isin)
                    security.add("figiCode", item["figi"])
                    security.add("ticker", item["ticker"])
                    security.add("type", item["securityType"])
                    yield security

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if entity.schema.is_a("Organization"):
            yield from self.match_organization(entity)
        if entity.schema.is_a("Security"):
            yield from self.match_security(entity)

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        if match.schema.is_a("Security"):
            yield match
        if match.schema.is_a("Organization"):
            name = match.first("name")
            if name is None:
                return
            yield match
            for item in self.search(name):
                # Only emit the securities which match the name of the positive match
                # to the company exactly. Skip everything else.
                if item["name"] != name:
                    continue

                figi = item["figi"]
                security = self.make_entity(match, "Security")
                security.id = self.make_security_id(figi)
                security.add("figiCode", figi)
                security.add("issuer", match)
                security.add("ticker", item["ticker"])
                security.add("type", item["securityType"])
                # if item["exchCode"] is not None:
                #     security.add("notes", f'exchange {item["exchCode"]}')
                security.add("description", item["securityDescription"])
                yield security
