import logging
from normality import collapse_spaces
from typing import Any, Dict, Iterable, Generator, Optional

from requests import Session

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig


log = logging.getLogger(__name__)
NOMINATIM = "https://nominatim.openstreetmap.org/search.php"


class NominatimEnricher(Enricher[DS]):
    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[Session] = None,
    ):
        super().__init__(dataset, cache, config, session)
        self.cache.preload(f"{NOMINATIM}%")

    def search_nominatim(self, address: CE) -> Iterable[Dict[str, Any]]:
        for full in address.get("full"):
            full_norm = collapse_spaces(full)
            params = {
                "q": full_norm,
                "countrycodes": address.get("country"),
                "format": "jsonv2",
                "accept-language": "en",
                "addressdetails": 1,
            }
            results = self.http_get_json_cached(NOMINATIM, params)
            log.info("OpenStreetMap geocoded [%s]: %d results", full, len(results))
            for result in results:
                yield result
                # FIXME: only best result for now.
                return

    def match(self, entity: CE) -> Generator[CE, None, None]:
        if not entity.schema.is_a("Address"):
            return

        for result in self.search_nominatim(entity):
            # pprint(result)
            addr = self.make_entity(entity, "Address")
            osm_type = result.get("osm_type")
            osm_id = result.get("osm_id")
            if osm_id is None or osm_type is None:
                continue
            addr.id = f"osm-{osm_type}-{osm_id}"
            addr.add("full", result["display_name"])
            # addr.add("latitude", result.get("lat"))
            # addr.add("longitude", result.get("lon"))
            addr_data: Dict[str, str] = result.get("address", {})
            addr.add("country", addr_data.get("country"))
            addr.add("country", addr_data.get("country_code"))
            addr.add("city", addr_data.get("city"))
            addr.add("state", addr_data.get("state"))
            addr.add("postalCode", addr_data.get("postcode"))
            yield addr

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        yield match
