import json
import logging
from normality import slugify
from typing import cast, Any, Dict, Generator, Optional
from urllib.parse import urlparse
from banal import ensure_dict
from followthemoney.types import registry
from requests import Session
from requests.exceptions import RequestException
from rigour.urls import build_url, ParamsType

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.enrich.common import EnrichmentAbort, EnrichmentException


log = logging.getLogger(__name__)


def parse_date(raw: Any) -> Optional[str]:
    return registry.date.clean(raw)


class OpenCorporatesEnricher(Enricher[DS]):
    COMPANY_SEARCH_API = "https://api.opencorporates.com/v0.4/companies/search"
    OFFICER_SEARCH_API = "https://api.opencorporates.com/v0.4/officers/search"
    UI_PART = "://opencorporates.com/"
    API_PART = "://api.opencorporates.com/v0.4/"

    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[Session] = None,
    ):
        super().__init__(dataset, cache, config, session)
        token_var = "${OPENCORPORATES_API_TOKEN}"
        self.api_token: Optional[str] = self.get_config_expand("api_token", token_var)
        self.quota_exceeded = False
        if self.api_token == token_var:
            self.api_token = None
        if self.api_token is None:
            log.warning("OpenCorporates has no API token (%s)" % token_var)
        self.cache.preload(f"{self.COMPANY_SEARCH_API}%")

    def oc_get_cached(self, url: str, params: ParamsType = None) -> Optional[Any]:
        url = build_url(url, params=params)
        response = self.cache.get(url, max_age=self.cache_days)
        if response is None:
            if self.quota_exceeded:
                return None
            hidden_url = build_url(url, params={"api_token": self.api_token})
            try:
                resp = self.session.get(hidden_url)
                resp.raise_for_status()
            except RequestException as rex:
                if rex.response is not None:
                    if rex.response.status_code in (403, 429):
                        log.info("OpenCorporates quota exceeded; using only cache now.")
                        self.quota_exceeded = True
                        return None
                    elif rex.response.status_code == 401:
                        raise EnrichmentAbort(
                            "Authorization failure: %s" % url
                        ) from rex
                msg = "HTTP fetch failed [%s]: %s" % (url, rex)
                raise EnrichmentException(msg) from rex
            response = resp.text
            self.cache.set(url, response)
        return json.loads(response)

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.matchable:
            return
        if entity.has("opencorporatesUrl"):
            # TODO: fetch entity here when we start to expand with content!
            return

        if entity.schema.name in ["Company", "Organization", "LegalEntity"]:
            yield from self.search_companies(entity)
        if entity.schema.name in ["Person", "LegalEntity", "Company", "Organization"]:
            # yield from self.search_officers(entity)
            pass

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        clone = self.make_entity(match, match.schema.name)
        clone.id = match.id
        clone.add("opencorporatesUrl", match.get("opencorporatesUrl"))
        yield clone

    # def expand_entity(self, entity):
    #     for url in entity.get("opencorporatesUrl", quiet=True):
    #         url = self.make_url(url)
    #         data = self.get_api(url).get("results", {})
    #         if "company" in data:
    #             yield from self.expand_company(entity, data)
    #         if "officer" in data:
    #             yield from self.expand_officer(data, officer=entity)

    def make_entity_id(self, url: str) -> str:
        parsed = urlparse(url)
        path = slugify(parsed.path, sep="-")
        return f"oc-{path}"

    def jurisdiction_to_country(self, juris: Optional[Any]) -> Optional[str]:
        if juris is None:
            return None
        return str(juris).split("_", 1)[0]

    def company_entity(
        self, ref: CE, data: Dict[str, Any], entity: Optional[CE] = None
    ) -> CE:
        if "company" in data:
            data = ensure_dict(data.get("company", data))
        oc_url = cast(Optional[str], data.get("opencorporates_url"))
        if oc_url is None:
            raise ValueError("Company has no URL: %r" % data)
        if entity is None:
            entity = self.make_entity(ref, "Company")
            entity.id = self.make_entity_id(oc_url)
        entity.add("name", data.get("name"))

        # TODO: make this an adjacent object?
        address: Dict[str, Any] = ensure_dict(data.get("registered_address"))
        entity.add("country", address.get("country"))

        juris = self.jurisdiction_to_country(data.get("jurisdiction_code"))
        entity.add("jurisdiction", juris)
        entity.add("alias", data.get("alternative_names"))
        entity.add("address", data.get("registered_address_in_full"))
        entity.add("sourceUrl", data.get("registry_url"))
        entity.add("legalForm", data.get("company_type"))
        inc_date = data.get("incorporation_date")
        entity.add("incorporationDate", parse_date(inc_date))
        dis_date = data.get("dissolution_date")
        entity.add("dissolutionDate", parse_date(dis_date))
        entity.add("status", data.get("current_status"))
        entity.add("registrationNumber", data.get("company_number"))
        entity.add("opencorporatesUrl", oc_url)
        source = data.get("source", {})
        entity.add("publisher", source.get("publisher"))
        entity.add("publisherUrl", source.get("url"))
        entity.add("retrievedAt", parse_date(source.get("retrieved_at")))
        for code in data.get("industry_codes", []):
            code = code.get("industry_code", code)
            entity.add("sector", code.get("description"))
        for previous in data.get("previous_names", []):
            entity.add("previousName", previous.get("company_name"))
        for alias in data.get("alternative_names", []):
            entity.add("alias", alias.get("company_name"))
        return entity

    # def officer_entity(self, data, entity=None):
    #     if "officer" in data:
    #         data = ensure_dict(data.get("officer", data))
    #     person = data.get("occupation") or data.get("date_of_birth")
    #     schema = "Person" if person else "LegalEntity"
    #     entity = model.make_entity(schema)
    #     entity.make_id(data.get("opencorporates_url"))
    #     entity.add("name", data.get("name"))
    #     entity.add("country", data.get("nationality"))
    #     entity.add("jurisdiction", data.get("jurisdiction_code"))
    #     entity.add("address", data.get("address"))
    #     entity.add("birthDate", data.get("date_of_birth"), quiet=True)
    #     entity.add("position", data.get("occupation"), quiet=True)
    #     entity.add("opencorporatesUrl", data.get("opencorporates_url"))
    #     source = data.get("source", {})
    #     entity.add("publisher", source.get("publisher"))
    #     entity.add("publisherUrl", source.get("url"))
    #     entity.add("retrievedAt", source.get("retrieved_at"))
    #     return entity

    def search_companies(self, entity: CE) -> Generator[CE, None, None]:
        countries = entity.get_type_values(registry.country)
        params = {"q": entity.caption, "sparse": True, "country_codes": countries}
        for page in range(1, 9):
            params["page"] = page
            results = self.oc_get_cached(self.COMPANY_SEARCH_API, params=params)
            if results is None:
                break

            # print(results)
            for company in results.get("results", {}).get("companies", []):
                proxy = self.company_entity(entity, company)
                yield proxy
            if page >= results.get("total_pages", 0):
                break

    # def search_officers(self, entity):
    #     params = self.get_query(entity)
    #     for page in range(1, 9):
    #         params["page"] = page
    #         url = self.make_url(self.OFFICER_SEARCH_API, params)
    #         results = self.get_api(url)
    #         officers = results.get("results", {}).get("officers")
    #         for officer in ensure_list(officers):
    #             proxy = self.officer_entity(officer)
    #             yield self.make_match(entity, proxy)
    #         if page >= results.get("total_pages", 0):
    #             break

    # def enrich_entity(self, entity):
    #     schema = entity.schema.name

    #     if schema in ["Person", "LegalEntity", "Company", "Organization"]:
    #         yield from self.search_officers(entity)

    # def expand_company(self, entity, data):
    #     data = ensure_dict(data.get("company", data))
    #     entity = self.company_entity(data, entity=entity)
    #     for officer in ensure_list(data.get("officers")):
    #         yield from self.expand_officer(officer, company=entity)
    #     yield entity

    # def expand_officer(self, data, entity=None, company=None):
    #     data = ensure_dict(data.get("officer", data))
    #     entity = self.officer_entity(data, entity=entity)
    #     yield entity

    #     company = self.company_entity(data.get("company"), entity=company)
    #     yield company

    #     if company.id and entity.id:
    #         directorship = model.make_entity("Directorship")
    #         directorship.make_id(data.get("opencorporates_url"), "Directorship")
    #         directorship.add("director", entity)
    #         directorship.add("startDate", data.get("start_date"))
    #         directorship.add("endDate", data.get("end_date"))
    #         directorship.add("organization", company)
    #         directorship.add("role", data.get("position"))
    #         yield directorship
