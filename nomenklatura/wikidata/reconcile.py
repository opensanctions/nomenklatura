import logging
from typing import Optional, Type
from followthemoney import Dataset, DS, SE, StatementEntity
from rigour.ids.wikidata import is_qid
from rigour.territories import get_territory_by_qid

from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.model import Item

log = logging.getLogger(__name__)

# Wikidata sex-or-gender (P21) items mapped to FtM gender values.
GENDERS = {"Q6581097": "male", "Q6581072": "female"}


def candidate_proxy(dataset: Dataset, item: Item) -> StatementEntity:
    """Project a Wikidata item into a minimal Person proxy for matching.

    Reach for this in the reconciliation loop to score a search hit against an
    OpenSanctions person. It is deliberately small — names, birth date, gender
    and citizenship, the fields the matcher leans on for people — and is *not*
    the enricher's `item_proxy`, whose property mapping, relationship graph,
    topics and wikilinks we don't want here.
    """
    proxy = StatementEntity.from_data(dataset, {"schema": "Person", "id": item.id})
    for label in item.labels:
        label.apply(proxy, "name")
    for alias in item.aliases:
        alias.apply(proxy, "name")
    for claim in item.claims:
        if claim.deprecated:
            continue
        if claim.property == "P569":
            claim.text.apply(proxy, "birthDate")
        elif claim.property == "P21":
            gender = GENDERS.get(claim.qid or "")
            if gender is not None:
                proxy.add("gender", gender)
        elif claim.property == "P27":
            territory = get_territory_by_qid(claim.qid)
            if territory is not None and territory.ftm_country is not None:
                proxy.add("country", territory.ftm_country)
    return proxy


def reconcile(
    resolver: Resolver[SE],
    store: Store[DS, SE],
    client: WikidataClient,
    dataset: Dataset,
    algorithm: Type[ScoringAlgorithm],
    threshold: float,
    aliases: bool = False,
    user: Optional[str] = None,
) -> None:
    """Match the persons in a store against Wikidata and auto-merge confident hits.

    For each person not already linked to a QID, search Wikidata for candidates,
    score each with the given algorithm, and — if the best score clears the
    threshold — record a POSITIVE resolver judgement linking the entity to that
    QID. This is the headless half of the reconcile tool: no UI, no human review,
    just the xref-style auto-merge applied to Wikidata search hits.
    """
    config = algorithm.default_config()
    view = store.default_view()
    resolver.begin()
    seen, merged = 0, 0
    for entity in view.entities():
        if not entity.schema.is_a("Person") or entity.id is None:
            continue
        current = resolver.get_canonical(entity.id)
        if is_qid(current):
            # Already linked to a Wikidata item on an earlier pass.
            continue
        seen += 1
        best_qid: Optional[str] = None
        best_score = 0.0
        for qid in client.search_items(entity, aliases=aliases):
            item = client.fetch_item(qid)
            if item is None:
                continue
            candidate = candidate_proxy(dataset, item)
            score = algorithm.compare(entity, candidate, config).score
            if score > best_score:
                best_score = score
                best_qid = item.id
        if best_qid is None or best_score <= threshold:
            continue
        if not resolver.check_candidate(current, best_qid):
            continue
        log.info("Auto-merge [%.3f]: %s <> %s", best_score, entity.id, best_qid)
        canonical = resolver.decide(
            entity.id, best_qid, Judgement.POSITIVE, user=user, score=best_score
        )
        store.update(canonical.id)
        merged += 1
    resolver.commit()
    log.info("Reconciled %d of %d unlinked persons to Wikidata.", merged, seen)
