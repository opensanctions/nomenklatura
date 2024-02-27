import io
import csv
import json
import logging
from lxml import etree

# from pprint import pprint
from itertools import product
from functools import lru_cache
from typing import cast, Set, Generator, Optional, Dict, Any
from urllib.parse import urljoin
from followthemoney.types import registry

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.enrich.common import EnrichmentAbort
from nomenklatura.util import fingerprint_name


log = logging.getLogger(__name__)

GN = "{http://www.geonames.org/ontology#}"
STATUS = {
    "tr-org:statusActive": "Active",
    "tr-org:statusInActive": "Inactive",
}


class PermIDEnricher(Enricher):
    MATCHING_API = "https://api-eit.refinitiv.com/permid/match"

    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
        token_var = "${PERMID_API_TOKEN}"
        self.api_token: Optional[str] = self.get_config_expand("api_token", token_var)
        if self.api_token == token_var:
            self.api_token = None
        if self.api_token is None:
            log.warning("PermID has no API token (%s)" % token_var)
        self.quota_exceeded = False

    def entity_to_queries(self, entity: CE) -> bytes:
        names = entity.get_type_values(registry.name, matchable=True)
        countries = entity.get("jurisdiction", quiet=True)
        if not len(countries):
            countries = entity.get_type_values(registry.country, matchable=True)
        country_set = {c.upper()[:2] for c in countries}
        if len(country_set) == 0:
            country_set.add("")
        if len(names) * len(country_set) < 999:
            country_set.add("")
        if len(names) * len(country_set) < 999:
            fp = fingerprint_name(entity.caption)
            if fp is not None and fp not in names:
                names.append(fp)
        for name in entity.get('name', quiet=True):
            if len(names) * len(country_set) >= 999:
                break
            fp = fingerprint_name(entity.caption)
            if fp is not None and fp not in names:
                names.append(fp)
        sio = io.StringIO()
        writer = csv.writer(sio, dialect=csv.unix_dialect, delimiter=",")
        # LocalID,Standard Identifier,Name,Country,Street,City,PostalCode,State,Website
        writer.writerow(["LocalID", "Standard Identifier", "Name", "Country"])
        lei_code = entity.first("leiCode", quiet=True)
        if lei_code is not None:
            lei_code = f"LEI:{lei_code}"
        else:
            lei_code = ""
        for name, country in list(product(names, country_set))[:999]:
            writer.writerow([entity.id, lei_code, name, country])
        sio.seek(0)
        return sio.getvalue().encode("utf-8")

    @lru_cache(maxsize=1000)
    def fetch_placename(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not value.startswith("http://sws.geonames.org/"):
            raise ValueError("Not a GeoNames URL: %s" % value)
        url = urljoin(value, "about.rdf")
        res = self.http_get_cached(url, cache_days=120)
        try:
            doc = etree.fromstring(res.encode("utf=8"))
        except Exception:
            log.warn("Invalid GeoNames response: %s", url)
            self.http_remove_cache(url)
            return None
        for code in doc.findall(".//%scountryCode" % GN):
            return code.text
        for name in doc.findall(".//%sname" % GN):
            return name.text
        return value

    def fetch_permid(self, url: str) -> Optional[Dict[str, Any]]:
        params = {"format": "json-ld"}
        hidden = {"access-token": self.api_token}
        res_raw = self.http_get_cached(url, params=params, hidden=hidden, cache_days=90)
        if not len(res_raw):
            self.http_remove_cache(url, params=params)
            log.info("Empty response from PermID: %s", url)
            return None
        return cast(Dict[str, Any], json.loads(res_raw))

    def fetch_perm_org(self, entity: CE, url: str) -> Optional[CE]:
        res = self.fetch_permid(url)
        if res is None:
            return None
        res.pop("@id", None)
        res.pop("@type", None)
        res.pop("@context", None)
        res.pop("hasPrimaryIndustryGroup", None)

        perm_id = res.pop("tr-common:hasPermId", url.rsplit("-", 1)[-1])
        lei_code = res.pop("tr-org:hasLEI", None)
        match = self.make_entity(entity, "Company")
        match.id = f"lei-{lei_code}" if lei_code is not None else f"permid-{perm_id}"
        match.add("sourceUrl", url)
        match.add("leiCode", lei_code)
        match.add("permId", perm_id)
        match.add("name", res.pop("vcard:organization-name", None))
        match.add("website", res.pop("hasURL", None))
        match.add("country", self.fetch_placename(res.pop("isDomiciledIn", None)))
        incorporated = self.fetch_placename(res.pop("isIncorporatedIn", None))
        match.add("jurisdiction", incorporated)
        inc_date = res.pop("hasLatestOrganizationFoundedDate", None)
        match.add("incorporationDate", inc_date)

        hq_addr = res.pop("mdaas:HeadquartersAddress", None)
        reg_addr = res.pop("mdaas:RegisteredAddress", None)
        for addr in (hq_addr, reg_addr):
            if addr is not None:
                addr = ", ".join(addr.split("\n"))
                addr = addr.replace(",,", ",").strip().strip(",")
                match.add("address", addr)
        status_uri = res.pop("hasActivityStatus", None)
        status = STATUS.get(status_uri)
        if status is None:
            log.warning("Unknown status: %s" % status_uri)
        match.add("status", status)
        match.add("phone", res.pop("tr-org:hasHeadquartersPhoneNumber", None))
        match.add("phone", res.pop("tr-org:hasRegisteredPhoneNumber", None))
        res.pop("tr-org:hasHeadquartersFaxNumber", None)
        res.pop("tr-org:hasRegisteredFaxNumber", None)

        quote = res.pop("hasOrganizationPrimaryQuote", None)
        if quote is not None:
            quote_res = self.fetch_permid(quote)
            if quote_res is not None:
                match.add("ticker", quote_res.pop("tr-fin:hasExchangeTicker", None))
                match.add("ricCode", quote_res.pop("tr-fin:hasRic", None))
                match.add("topics", "corp.public")
        return match

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if self.quota_exceeded:
            return
        if not entity.schema.is_a("Organization"):
            return
        try:
            for permid in entity.get('permId', quiet=True):
                permid_url = f"https://permid.org/1-{permid}"
                match = self.fetch_perm_org(entity, permid_url)
                if match is not None:
                    yield match
            headers = {
                "x-openmatch-numberOfMatchesPerRecord": "4",
                "X-AG-Access-Token": self.api_token,
                "x-openmatch-dataType": "Organization",
            }
            cache_key = f"permid:{entity.id}"
            query = self.entity_to_queries(entity)
            res = self.http_post_json_cached(
                self.MATCHING_API,
                cache_key,
                data=query,
                headers=headers,
                retry=0,
                cache_days=self.cache_days,
            )
            seen_matches: Set[str] = set()
            for result in res.get("outputContentResponse", []):
                match_permid_url = result.get("Match OpenPermID")
                if match_permid_url is None or match_permid_url in seen_matches:
                    continue
                seen_matches.add(match_permid_url)
                match = self.fetch_perm_org(entity, match_permid_url)
                if match is not None:
                    yield match
        except EnrichmentAbort as exc:
            self.quota_exceeded = True
            log.warning("PermID quota exceeded: %s", exc)

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        yield match
