import os
import requests
import logging
from banal import hash_data
from typing import Generator, Optional
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

        user = os.environ.get("BQ_USER")
        password = os.environ.get("BQ_PASS")
        if not user or not password:
            raise ValueError("Missing BrightQuery credentials: BQ_USER and/or BQ_PASS")

        self.session.auth = (user, password)

    def match(self, entity: SE) -> Generator[SE, None, None]:
        if not entity.schema.is_a("Organization"):
            log.debug("Skipping non-Organization entity: %s", entity)
            return
        # Get the name and address to search
        names = entity.get("name")
        addresses = entity.get("address")
        for name in names:
            for address in addresses:
                payload = {
                    "company_name": name,
                    "address": address,
                }

                cache_id = entity.id or hash_data(payload)
                cache_key = f"{self.BASE_URL}:{cache_id}"

                # Cached POST request to BrightQuery
                response = self.http_post_json_cached(self.BASE_URL, cache_key, payload)
                if not response:
                    continue

                # Extract children nodes from the BQ response
                children = response.get("root", {}).get("children", [])
                for child in children:
                    company_name = child.get("bq_organization_name")
                    print(f"Found company: {company_name}")
                    if not company_name:
                        continue

                    proxy = self.make_entity(entity, "Company")
                    proxy.id = make_entity_id(child.get("bq_organization_id"))
                    proxy.add("name", company_name)
                    # proxy.add("legal_name", child.get("bq_organization_legal_name"))
                    proxy.add(
                        "registrationNumber",
                        child.get("bq_organization_company_number"),
                    )
                    # proxy.add("company_type", child.get("bq_organization_company_type"))
                    proxy.add(
                        "incorporationDate", child.get("bq_organization_date_founded")
                    )
                    proxy.add("website", child.get("bq_organization_website"))
                    proxy.add("website", child.get("bq_organization_linkedin_url"))
                    # proxy.add("topics", "corp.public")

                    yield proxy

    def expand(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        if match.schema.is_a("Organization"):
            name = match.first("name")
            if name is None:
                return
            yield match
