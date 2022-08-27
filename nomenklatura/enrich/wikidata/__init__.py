import logging
from functools import cache
from typing import cast, Generator, Any, Dict, Optional, Set
from followthemoney.helpers import check_person_cutoff

from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.cache import Cache
from nomenklatura.enrich.wikidata.lang import pick_obj_lang
from nomenklatura.enrich.wikidata.qualified import qualify_value
from nomenklatura.enrich.wikidata.props import (
    PROPS_ASSOCIATION,
    PROPS_DIRECT,
    PROPS_FAMILY,
    PROPS_QUALIFIED,
    PROPS_TOPICS,
)
from nomenklatura.enrich.wikidata.model import Claim, Item
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.util import is_qid

WD_API = "https://www.wikidata.org/w/api.php"
log = logging.getLogger(__name__)


class WikidataEnricher(Enricher):
    def __init__(self, dataset: DS, cache: Cache, config: EnricherConfig):
        super().__init__(dataset, cache, config)
        self.depth = self.get_config_int("depth", 1)
        self.label_cache_days = self.get_config_int("label_cache_days", 100)
        self.cache.preload(f"{WD_API}%")

    def keep_entity(self, entity: CE) -> bool:
        if check_person_cutoff(entity):
            return False
        return True

    def match(self, entity: CE) -> Generator[CE, None, None]:
        wikidata_id = self.get_wikidata_id(entity)

        # Already has an ID associated with it:
        if wikidata_id is not None:
            item = self.fetch_item(wikidata_id)
            if item is not None:
                proxy = self.item_proxy(entity, item, schema=entity.schema.name)
                if proxy is not None and self.keep_entity(proxy):
                    yield proxy
            return

        if not entity.schema.is_a("Person"):
            return

        for name in entity.get("name", quiet=True):
            params = {
                "format": "json",
                "search": name,
                "action": "wbsearchentities",
                "language": "de",
            }
            data = self.http_get_json_cached(WD_API, params=params)
            if "search" not in data:
                self.http_remove_cache(WD_API, params=params)
                log.warning("Search response [%s] does not include results" % name)
                continue
            for result in data["search"]:
                item = self.fetch_item(result["id"])
                if item is not None:
                    proxy = self.item_proxy(entity, item, schema=entity.schema.name)
                    if proxy is not None and self.keep_entity(proxy):
                        yield proxy

    def expand(self, entity: CE, match: CE) -> Generator[CE, None, None]:
        wikidata_id = self.get_wikidata_id(match)
        if wikidata_id is None:
            return
        item = self.fetch_item(wikidata_id)
        if item is None:
            return
        proxy = self.item_proxy(match, item, schema=match.schema.name)
        if proxy is None or not self.keep_entity(proxy):
            return
        if "role.pep" in entity.get("topics", quiet=True):
            proxy.add("topics", "role.pep")
        yield proxy
        yield from self.item_graph(proxy, item)

    def get_wikidata_id(self, entity: CE) -> Optional[str]:
        if is_qid(entity.id):
            return str(entity.id)
        for value in entity.get("wikidataId", quiet=True):
            if is_qid(value):
                return value
        return None

    def wikibase_getentities(
        self, id: str, cache_days: Optional[int] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        # https://www.mediawiki.org/wiki/Wikibase/API
        # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
        params = {**kwargs, "format": "json", "ids": id, "action": "wbgetentities"}
        data = self.http_get_json_cached(WD_API, params=params, cache_days=cache_days)
        return cast(Dict[str, Any], data)

    def fetch_item(self, qid: str, cache_days: Optional[int] = None) -> Optional[Item]:
        cache_days = self.cache_days if cache_days is None else cache_days
        data = self.wikibase_getentities(qid, cache_days=cache_days)
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return None
        return Item(entity)

    @cache
    def get_label(self, qid: str) -> Optional[str]:
        data = self.wikibase_getentities(
            qid,
            cache_days=self.label_cache_days,
            props="labels",
        )
        entity = data.get("entities", {}).get(qid)
        label = pick_obj_lang(entity.get("labels", {}))
        return label

    def make_link(
        self,
        proxy: CE,
        claim: Claim,
        depth: int,
        seen: Set[str],
        schema: str,
        other_schema: str,
        source_prop: str,
        target_prop: str,
    ) -> Generator[CE, None, None]:
        if depth < 1 or claim.qid is None or claim.qid in seen:
            return
        item = self.fetch_item(claim.qid)
        if item is None:
            return

        other = self.item_proxy(proxy, item, schema=other_schema)
        if other is None or not self.keep_entity(other):
            return
        # Hacky: if an entity is a PEP, then by definition their relatives and
        # associates are RCA (relatives and close associates).
        if "role.pep" in proxy.get("topics", quiet=True):
            if "role.pep" not in other.get("topics"):
                other.add("topics", "role.rca")
        yield other
        yield from self.item_graph(other, item, depth=depth - 1, seen=seen)
        link = self.make_entity(proxy, schema)
        min_id, max_id = sorted((proxy.id, other.id))
        link.id = f"wd-{claim.property}-{min_id}-{max_id}"
        link.id = link.id.lower()
        link.add(source_prop, proxy.id)
        link.add(target_prop, item.id)
        rel = claim.property_label(self)
        link.add("relationship", rel)

        for qual in claim.get_qualifier("P580"):
            text = qual.text(self)
            link.add("startDate", text)

        for qual in claim.get_qualifier("P582"):
            text = qual.text(self)
            link.add("endDate", text)

        for qual in claim.get_qualifier("P585"):
            text = qual.text(self)
            link.add("date", text)

        for qual in claim.get_qualifier("P1039"):
            text = qual.text(self)
            link.set("relationship", text)

        for qual in claim.get_qualifier("P2868"):
            text = qual.text(self)
            link.set("relationship", text)

        for ref in claim.references:
            for snak in ref.get("P854"):
                text = snak.text(self)
                link.add("sourceUrl", text)
        yield link

    def item_graph(
        self,
        proxy: CE,
        item: Item,
        depth: Optional[int] = None,
        seen: Optional[Set[str]] = None,
    ) -> Generator[CE, None, None]:
        if seen is None:
            seen = set()
        seen = seen.union([item.id])
        if depth is None:
            depth = self.depth
        for claim in item.claims:
            # TODO: memberships, employers?
            if claim.property in PROPS_FAMILY:
                yield from self.make_link(
                    proxy,
                    claim,
                    depth,
                    seen,
                    schema="Family",
                    other_schema="Person",
                    source_prop="person",
                    target_prop="relative",
                )
                continue
            if claim.property in PROPS_ASSOCIATION:
                yield from self.make_link(
                    proxy,
                    claim,
                    depth,
                    seen,
                    schema="Associate",
                    other_schema="Person",
                    source_prop="person",
                    target_prop="associate",
                )
                continue

    def item_proxy(self, ref: CE, item: Item, schema: str = "Person") -> Optional[CE]:
        proxy = self.make_entity(ref, schema)
        proxy.id = item.id
        if item.modified is None:
            return None
        proxy.add("modifiedAt", item.modified)
        proxy.add("wikidataId", item.id)
        proxy.add("name", item.label)
        proxy.add("notes", item.description)
        proxy.add("alias", item.aliases)

        if proxy.schema.is_a("Person") and not item.is_instance("Q5"):
            log.debug("Person is not a Q5 [%s]: %s", item.id, item.label)
            return None

        for claim in item.claims:
            if claim.property is None:
                continue
            ftm_prop = PROPS_DIRECT.get(claim.property)
            if ftm_prop is None:
                continue
            if ftm_prop not in proxy.schema.properties:
                log.info("Entity %s does not have property: %s", proxy.id, ftm_prop)
                continue
            value = claim.text(self)
            if ftm_prop in PROPS_QUALIFIED and value is not None:
                value = qualify_value(self, value, claim)
            if ftm_prop == "topics" and claim.qid is not None:
                value = PROPS_TOPICS.get(claim.qid)
            proxy.add(ftm_prop, value)
        return proxy
