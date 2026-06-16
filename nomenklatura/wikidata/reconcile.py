import logging
from typing import List, Optional, Set, Tuple, Type
from followthemoney import Dataset, DS, SE, StatementEntity, registry
from rigour.ids.wikidata import is_qid
from rigour.territories import get_territory_by_qid

from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.matching.types import ScoringConfig
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.lang import LangText
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.util import entity_qid
from nomenklatura.wikidata.propose import propose_create, propose_enrich
from nomenklatura.wikidata.props import PROPS_DIRECT, PROPS_QUALIFIED, PROPS_TOPICS
from nomenklatura.wikidata.qualified import qualify_value
from nomenklatura.wikidata.value import clean_wikidata_name, is_alias_strong
from nomenklatura.wikidata.write import QSCommand

log = logging.getLogger(__name__)

# How often to commit the API-response cache. Each person triggers several
# (slow) Wikidata calls, so a long run that's cancelled would otherwise lose
# every cached response; flushing periodically keeps the work that's done.
CACHE_INTERVAL = 10


def candidate_proxy(dataset: Dataset, item: Item) -> Optional[StatementEntity]:
    """Project a Wikidata item into a Person proxy for matching and display.

    Reach for this in the reconciliation loop to score and show a search hit
    against an OpenSanctions person. It mirrors the enricher's `item_proxy`
    single-entity projection — names, aliases, the full direct-property set,
    citizenship via territory, description and Wikipedia link — so the matcher
    sees the same evidence the enricher would, and the reviewer sees enough to
    judge. (It duplicates `item_proxy` for now rather than coupling to the
    enricher; the relationship graph is deliberately left out.) Returns None for
    a non-human item, which isn't a person match.
    """
    if item.modified is None:
        return None
    proxy = StatementEntity.from_data(dataset, {"schema": "Person", "id": item.id})
    proxy.add("wikidataId", item.id)
    names: Set[str] = set()
    for label in item.sorted_labels:
        if label.text is None:
            continue
        ltext = label.text.casefold()
        if ltext in names:
            continue
        label.apply(proxy, "name", clean=clean_wikidata_name)
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
            alias.apply(proxy, "alias", clean=clean_wikidata_name)
            names.add(ltext)
        else:
            alias.apply(proxy, "weakAlias", clean=clean_wikidata_name)

    if not item.is_instance("Q5"):
        log.debug("Item is not a human [%s]: %s", item.id, item.labels)
        return None

    names_concat = " ".join(names)
    for claim in item.claims:
        if claim.property is None:
            continue
        ftm_prop = PROPS_DIRECT.get(claim.property)
        if ftm_prop is None or ftm_prop not in proxy.schema.properties:
            continue
        ftm_prop_ = proxy.schema.get(ftm_prop)
        if ftm_prop_ is None:
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
        # Make sure the aliases look like the main name, else mark them weak:
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

    for wikilink in item.wikilinks:
        if wikilink.site == "enwiki":
            proxy.add("wikipediaUrl", wikilink.url, lang=wikilink.lang)
            break
    return proxy


def create_preview(dataset: Dataset, person: SE) -> StatementEntity:
    """A placeholder entity standing in for the new item in the comparison.

    We deliberately don't project the person's values: the new item's contents
    are whatever `propose_create` emits, and a populated preview would imply a
    fidelity we don't promise. Just a labelled stub so the "create" option
    renders in the same comparison table as a candidate.
    """
    proxy = StatementEntity.from_data(dataset, {"schema": "Person", "id": "QNEW"})
    proxy.add("name", "[NEW ITEM]")
    return proxy


def rank_candidates(
    client: WikidataClient,
    dataset: Dataset,
    algorithm: Type[ScoringAlgorithm],
    config: ScoringConfig,
    entity: SE,
    aliases: bool = False,
) -> List[Tuple[Item, float]]:
    """Search Wikidata for an entity and return its candidate items, best first.

    Shared by the headless and interactive reconcile paths: it runs the search,
    fetches each hit, projects it with `candidate_proxy`, scores it against the
    entity, and returns `(item, score)` pairs sorted by descending score. Items
    that aren't human (no proxy) are dropped.
    """
    scored: List[Tuple[Item, float]] = []
    for qid in client.search_items(entity, aliases=aliases):
        item = client.fetch_item(qid)
        if item is None:
            continue
        candidate = candidate_proxy(dataset, item)
        if candidate is None:
            continue
        score = algorithm.compare(entity, candidate, config).score
        scored.append((item, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def reconcile(
    resolver: Resolver[SE],
    store: Store[DS, SE],
    client: WikidataClient,
    dataset: Dataset,
    algorithm: Type[ScoringAlgorithm],
    threshold: float,
    aliases: bool = False,
    user: Optional[str] = None,
    retrieved: Optional[str] = None,
) -> Tuple[List[QSCommand], List[QSCommand]]:
    """Match the persons in a store against Wikidata, auto-merge, and emit QS.

    For each person: those already linked to a QID are diffed against their
    Wikidata item into enrichment commands; those matched above the threshold are
    recorded as POSITIVE judgements but *not* enriched (an auto-merge is a guess,
    and we only push edits from links we already trust — they enrich on a later
    pass once linked); those with no acceptable match become item-creation
    commands. Returns `(enrich_commands, create_commands)` for the caller to
    serialize into the two QuickStatements batches. This is the headless half of
    the reconcile tool: no UI, just xref-style auto-merge plus reviewable QS.
    """
    config = algorithm.default_config()
    view = store.default_view()
    resolver.begin()
    enrich_commands: List[QSCommand] = []
    create_commands: List[QSCommand] = []
    seen, merged = 0, 0
    for index, entity in enumerate(view.entities()):
        if index and index % CACHE_INTERVAL == 0:
            client.cache.flush()
        if not entity.schema.is_a("Person") or entity.id is None:
            continue
        current = resolver.get_canonical(entity.id)
        # Linked either by a resolver merge (canonical is a QID) or by the entity
        # carrying its own QID (id or wikidataId property): enrich, don't search.
        linked = current if is_qid(current) else entity_qid(entity)
        if linked is not None:
            item = client.fetch_item(linked)
            if item is not None:
                enrich_commands.extend(propose_enrich(entity, item, retrieved))
            continue
        seen += 1
        ranked = rank_candidates(client, dataset, algorithm, config, entity, aliases)
        best_item, best_score = ranked[0] if ranked else (None, 0.0)
        if (
            best_item is not None
            and best_score > threshold
            and resolver.check_candidate(current, best_item.id)
        ):
            # Record the link, but don't enrich off it: an auto-merge is an
            # unconfirmed guess, and we only push Wikidata edits from links we
            # already trust. It gets enriched on a later pass as "already linked".
            log.info("Auto-merge [%.3f]: %s <> %s", best_score, entity.id, best_item.id)
            canonical = resolver.decide(
                entity.id, best_item.id, Judgement.POSITIVE, user=user, score=best_score
            )
            store.update(canonical.id)
            merged += 1
        else:
            # No acceptable match: propose a new Wikidata item for review.
            create_commands.extend(propose_create(entity, retrieved))
    resolver.commit()
    log.info("Reconciled %d of %d unlinked persons to Wikidata.", merged, seen)
    return enrich_commands, create_commands
