import requests
import logging
from banal import hash_data
from typing import Generator, Optional, Dict, Any
from followthemoney.util import make_entity_id
from followthemoney import DS, SE

from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig

log = logging.getLogger(__name__)


class BrightQueryEnricher(Enricher[DS]):
    """Enricher for the BrightQuery Business Identity API."""

    BASE_URL = "https://apigateway.brightquery.com/auth/business-identity-api/org"

    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[requests.Session] = None,
    ):
        super().__init__(dataset, cache, config, session)
        user_var = "${BRIGHTQUERY_USERNAME}"
        pass_var = "${BRIGHTQUERY_PASSWORD}"
        self._user = self.get_config_expand("username", user_var)
        self._password = self.get_config_expand("password", pass_var)
        if not self._user or not self._password:
            raise ValueError(
                "Missing BrightQuery credentials: brightquery_user and/or brightquery_pass"
            )

        self.session.auth = (self._user, self._password)

    def create_proxy(
        self, entity: SE, child: Dict[str, Any]
    ) -> Generator[SE, None, None]:
        # Primary, most common name of the Organization, which equals the name of
        # the ultimate parent or sole entity that comprises the Organization.
        org_name = child.get("bq_organization_name")
        # Some records do not have Legal Entity names. Then we fall back to the org_name.
        name = child.get("bq_legal_entity_name") or org_name
        if not name:
            log.warning(
                "BrightQuery record without name: %s",
                child.get("bq_legal_entity_id"),
            )
            return
        # Unique ID of the Organization. An Organization is the concept of a company,
        # which is constructed as a collection of Legal Entities (child and parent entities)
        # and Locations (e.g., offices, stores).
        bq_org_id = child.get("bq_organization_id")
        # Unique ID of the Legal Entity. A Legal Entity is part of an Organization and is
        # registered with the Secretary of State of a jurisdiction.
        # LegalEntity is the primary object of interest for our processing.
        bq_entity_id = child.get("bq_legal_entity_id")
        proxy = self.make_entity(entity, "Company")
        proxy.id = f"brightquery-{make_entity_id(name, bq_entity_id)}"
        # Legal name of the Legal Entity
        proxy.add("name", name)
        proxy.add("brightQueryOrgId", bq_org_id)
        proxy.add("brightQueryId", bq_entity_id)
        # Link to the Organization's primary website.
        proxy.add("website", child.get("bq_website"))
        proxy.add("address", child.get("bq_legal_entity_address_summary"))
        # Jurisdiction code (2-digit state name) in which the Legal Entity is registered,
        # typically with the Secretary of State.
        proxy.add("jurisdiction", child.get("bq_legal_entity_jurisdiction_code"))
        # Date on which the Legal Entity was registered with the Secretary of State.
        proxy.add(
            "incorporationDate",
            child.get("bq_legal_entity_date_founded"),
        )
        yield proxy

    def search(self, payload: dict[str, Any]) -> Generator[Dict[str, str], None, None]:
        cache_id = hash_data(payload)
        cache_key = f"{self.BASE_URL}:{cache_id}"

        # We have to re-implement http_post_json_cached here because the endpoint doesn't
        # return JSON when there are no results.
        resp_data = self.cache.get_json(cache_key, max_age=self.cache_days)
        if not resp_data:
            response = self.session.post(self.BASE_URL, json=payload, timeout=15)
            # When no results are found, the API helpfully doesn't return JSON
            # but just a 204 with an empty response body.
            if response.status_code == 204:
                # Cache the empty result to avoid hitting the API again
                # for the same query.
                self.cache.set_json(cache_key, {})
                return
            response.raise_for_status()
            resp_data = response.json()
            self.cache.set_json(cache_key, resp_data)
        # Number of records per hit is 10. Records are sorted by revenue and employees headcount.
        children = resp_data.get("root", {}).get("children", [])
        yield from children

    def match(self, entity: SE) -> Generator[SE, None, None]:
        # Get the name and address to search
        names = entity.get("name")
        addresses = entity.get("address")
        for name in names:
            if addresses:
                # If we have an address, we can search by both name and address
                for address in addresses:
                    payload = {"company_name": name, "address": address}
                    for match in self.search(payload):
                        yield from self.create_proxy(entity, match)
            else:
                # If we don't have an address, just search by name
                payload = {"company_name": name}
                for match in self.search(payload):
                    yield from self.create_proxy(entity, match)

    def expand(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        yield match
