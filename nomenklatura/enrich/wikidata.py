import logging
from typing import Generator, Optional, Set
from followthemoney.helpers import check_person_cutoff
from followthemoney import StatementEntity, registry, DS, SE
from requests import Session
from rigour.ids.wikidata import is_qid
from rigour.territories import get_territory_by_qid

from nomenklatura.cache import Cache
from nomenklatura.enrich.common import Enricher, EnricherConfig
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.lang import LangText
from nomenklatura.wikidata.model import Claim, Item
from nomenklatura.wikidata.props import (
    PROPS_ASSOCIATION,
    PROPS_DIRECT,
    PROPS_FAMILY,
    PROPS_QUALIFIED,
    PROPS_TOPICS,
)
from nomenklatura.wikidata.qualified import qualify_value
from nomenklatura.wikidata.value import clean_name, is_alias_strong

log = logging.getLogger(__name__)


class WikidataEnricher(Enricher[DS]):
    def __init__(
        self,
        dataset: DS,
        cache: Cache,
        config: EnricherConfig,
        session: Optional[Session] = None,
    ):
        super().__init__(dataset, cache, config, session)
        self.depth = self.get_config_int("depth", 1)
        self.client = WikidataClient(cache, self.session, cache_days=self.cache_days)

    def keep_entity(self, entity: StatementEntity) -> bool:
        if check_person_cutoff(entity):
            return False
        return True

    def match(self, entity: SE) -> Generator[SE, None, None]:
        if not entity.schema.is_a("Person"):
            return

        wikidata_id = self.get_wikidata_id(entity)

        # Already has an ID associated with it:
        if wikidata_id is not None:
            item = self.client.fetch_item(wikidata_id)
            if item is not None:
                proxy = self.item_proxy(entity, item, schema=entity.schema.name)
                if proxy is not None and self.keep_entity(proxy):
                    yield proxy
            return

        for name in entity.get("name", quiet=True):
            params = {
                "format": "json",
                "search": name,
                "action": "wbsearchentities",
                "language": "en",
                "strictlanguage": "false",
            }
            data = self.http_get_json_cached(WikidataClient.WD_API, params=params)
            if "search" not in data:
                self.http_remove_cache(WikidataClient.WD_API, params=params)
                log.info("Search response [%s] does not include results" % name)
                continue
            for result in data["search"]:
                item = self.client.fetch_item(result["id"])
                if item is not None:
                    proxy = self.item_proxy(entity, item, schema=entity.schema.name)
                    if proxy is not None and self.keep_entity(proxy):
                        yield proxy

    def expand(self, entity: SE, match: SE) -> Generator[SE, None, None]:
        wikidata_id = self.get_wikidata_id(match)
        if wikidata_id is None:
            return
        item = self.client.fetch_item(wikidata_id)
        if item is None:
            return
        proxy = self.item_proxy(match, item, schema=match.schema.name)
        if proxy is None or not self.keep_entity(proxy):
            return
        if "role.pep" in entity.get("topics", quiet=True):
            proxy.add("topics", "role.pep")
        yield proxy
        yield from self.item_graph(proxy, item)

    def get_wikidata_id(self, entity: StatementEntity) -> Optional[str]:
        if entity.id is not None and is_qid(entity.id):
            return str(entity.id)
        for value in entity.get("wikidataId", quiet=True):
            if is_qid(value):
                return value
        return None

    def make_link(
        self,
        proxy: SE,
        claim: Claim,
        depth: int,
        seen: Set[str],
        schema: str,
        other_schema: str,
        source_prop: str,
        target_prop: str,
    ) -> Generator[SE, None, None]:
        if depth < 1 or claim.qid is None or claim.qid in seen:
            return
        item = self.client.fetch_item(claim.qid)
        if item is None:
            return

        other = self.item_proxy(proxy, item, schema=other_schema)
        if other is None or not self.keep_entity(other):
            return None
        if proxy.id is None or other.id is None:
            return None
        # Hacky: if an entity is a PEP, then by definition their relatives and
        # associates are RCA (relatives and close associates).
        if "role.pep" in proxy.get("topics", quiet=True):
            if "role.pep" not in other.get("topics"):
                other.add("topics", "role.rca")
        yield other
        yield from self.item_graph(other, item, depth=depth - 1, seen=seen)
        link = self.make_entity(proxy, schema)
        min_id, max_id = sorted((proxy.id, other.id))
        # FIXME: doesn't lead to collisions because claim.property has an inverse:
        link.id = f"wd-{claim.property}-{min_id}-{max_id}"
        link.id = link.id.lower()
        link.add(source_prop, proxy.id)
        link.add(target_prop, item.id)
        claim.property_label.apply(link, "relationship")

        for qual in claim.get_qualifier("P580"):
            qual.text.apply(link, "startDate")

        for qual in claim.get_qualifier("P582"):
            qual.text.apply(link, "endDate")

        for qual in claim.get_qualifier("P585"):
            qual.text.apply(link, "date")

        for qual in claim.get_qualifier("P1039"):
            qual.text.apply(link, "relationship")

        for qual in claim.get_qualifier("P2868"):
            qual.text.apply(link, "relationship")

        for ref in claim.references:
            for snak in ref.get("P854"):
                snak.text.apply(link, "sourceUrl")
        yield link

    def item_graph(
        self,
        proxy: SE,
        item: Item,
        depth: Optional[int] = None,
        seen: Optional[Set[str]] = None,
    ) -> Generator[SE, None, None]:
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

    def item_proxy(self, ref: SE, item: Item, schema: str = "Person") -> Optional[SE]:
        proxy = self.make_entity(ref, schema)
        proxy.id = item.id
        if item.modified is None:
            return None
        # proxy.add("modifiedAt", item.modified)
        proxy.add("wikidataId", item.id)
        names: Set[str] = set()
        for label in item.sorted_labels:
            if label.text is None:
                continue
            ltext = label.text.casefold()
            if ltext in names:
                continue
            label.apply(proxy, "name", clean=clean_name)
            names.add(ltext)
        if item.description is not None:
            item.description.apply(proxy, "notes")
        for alias in item.sorted_aliases:
            if alias.text is None:
                continue
            ltext = alias.text.casefold()
            if ltext in names:
                continue
            if is_alias_strong(alias.text, names):
                alias.apply(proxy, "alias", clean=clean_name)
                names.add(ltext)
            else:
                alias.apply(proxy, "weakAlias", clean=clean_name)

        if proxy.schema.is_a("Person") and not item.is_instance("Q5"):
            log.debug("Person is not a Q5 [%s]: %s", item.id, item.labels)
            return None

        names_concat = " ".join(names)
        for claim in item.claims:
            if claim.property is None:
                continue
            ftm_prop = PROPS_DIRECT.get(claim.property)
            if ftm_prop is None:
                continue
            if ftm_prop not in proxy.schema.properties:
                log.info("Entity %s does not have property: %s", proxy.id, ftm_prop)
                continue
            ftm_prop_ = proxy.schema.get(ftm_prop)
            if ftm_prop_ is None:
                log.info("Entity %s does not have property: %s", proxy.id, ftm_prop)
                continue
            if ftm_prop_.type == registry.country:
                territory = get_territory_by_qid(claim.qid)
                if territory is None or territory.ftm_country is None:
                    continue
                value = LangText(territory.ftm_country, original=claim.qid)
            else:
                value = claim.text

            # Sanity check that the name parts are in any of the full names:
            if ftm_prop in ("firstName", "lastName", "fatherName"):
                if value.text is None or value.text.lower() not in names_concat:
                    continue

            # Make sure the aliases look like the main name, otherwise mark them as weak:
            if ftm_prop == "alias":
                if value.text is None or value.text.lower() in names:
                    continue
                _strong = is_alias_strong(value.text, names)
                ftm_prop = "alias" if _strong else "weakAlias"

            if ftm_prop in PROPS_QUALIFIED:
                value = qualify_value(value, claim)
            if ftm_prop == "topics":
                topic = PROPS_TOPICS.get(claim.qid or "")
                if topic is None:
                    continue
                value = LangText(topic, original=claim.qid)
            value.apply(proxy, ftm_prop)
        return proxy
