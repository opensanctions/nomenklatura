import json
import logging
from pprint import pprint
from normality import collapse_spaces
from typing import Dict, Iterable, Generator
from requests.exceptions import RequestException

from nomenklatura.entity import CE
from nomenklatura.enrich.common import Enricher


log = logging.getLogger(__name__)
NOMINATIM = "https://nominatim.openstreetmap.org/search.php"


class NominatimEnricher(Enricher):
    def search_nominatim(self, address: CE) -> Iterable[Dict[str, str]]:
        for full in address.get("full"):
            full_norm = collapse_spaces(full)
            params = {
                "q": full_norm,
                "countrycodes": address.get("country"),
                "format": "jsonv2",
                "accept-language": "en",
                "addressdetails": 1,
            }
            try:
                response = self.http_get_cached(NOMINATIM, params)
            except RequestException:
                log.exception("Failed to geocode: %s", full)
                continue
            results = json.loads(response)
            log.info("OpenStreetMap geocoded [%s]: %d results", full, len(results))
            for result in results:
                yield result

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.is_a("Address"):
            return

        for result in self.search_nominatim(entity):
            # pprint(result)
            addr = self.make_entity(entity, "Address")
            osm_type = result["osm_type"]
            osm_id = result["osm_id"]
            addr.id = f"osm-{osm_type}-{osm_id}"
            addr.add("full", result["display_name"])
            # TODO:
            print("-> ", repr(addr))
            yield addr

    def expand(self, entity: CE) -> Generator[CE, None, None]:
        yield entity
