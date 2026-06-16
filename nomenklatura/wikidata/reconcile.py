import logging
from typing import List, Optional, Tuple, Type
from followthemoney import Dataset, DS, SE, StatementEntity
from rigour.ids.wikidata import is_qid
from rigour.territories import get_territory_by_qid

from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.propose import propose_create, propose_enrich
from nomenklatura.wikidata.write import QSCommand

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
    for entity in view.entities():
        if not entity.schema.is_a("Person") or entity.id is None:
            continue
        current = resolver.get_canonical(entity.id)
        if is_qid(current):
            # Already linked to a Wikidata item on an earlier pass: enrich it.
            item = client.fetch_item(current)
            if item is not None:
                enrich_commands.extend(propose_enrich(entity, item, retrieved))
            continue
        seen += 1
        best_item: Optional[Item] = None
        best_score = 0.0
        for qid in client.search_items(entity, aliases=aliases):
            item = client.fetch_item(qid)
            if item is None:
                continue
            log.info("Comparing %s to %s (%s)", entity.id, item.id, item.label)
            candidate = candidate_proxy(dataset, item)
            score = algorithm.compare(entity, candidate, config).score
            if score > best_score:
                best_score = score
                best_item = item
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
