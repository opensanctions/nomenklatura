import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from followthemoney import registry, StatementEntity
from rigour.langs import iso_639_alpha2
from rigour.territories import get_territory

from nomenklatura.wikidata.lang import MULTI_LANG
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.write import (
    QSCommand,
    CreateItem,
    SetLabel,
    SetAlias,
    AddStatement,
    QSValue,
    Snak,
    LAST,
    url_reference,
)

log = logging.getLogger(__name__)

# FtM gender → Wikidata sex-or-gender (P21) item. We only ever assert male/female:
# there is no clean canonical QID for FtM's "other", and pushing a guessed gender
# from a screening dataset onto a Wikidata person is not an edit we want to make.
GENDER_QIDS = {"male": "Q6581097", "female": "Q6581072"}


@dataclass
class PositionClaim:
    """A position to assert as P39, already resolved to a Wikidata QID.

    Reach for this as the input to position enrichment: the reconcile walk
    traverses Person → Occupancy → Position and hands these in, so this emitter
    stays free of the store. `start`/`end` are the curated qualifier dates
    (`startDate ?? periodStart`, `endDate ?? periodEnd`) or None when unknown.
    """

    qid: str
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass
class _Known:
    """What Wikidata already holds, so the diff only emits what's missing."""

    is_human: bool = False
    has_birth_date: bool = False
    has_gender: bool = False
    citizenship_qids: Set[str] = field(default_factory=set)
    position_qids: Set[str] = field(default_factory=set)
    # Casefolded label + alias texts, to avoid re-adding a name WD already lists.
    name_texts: Set[str] = field(default_factory=set)


def _known_from_item(item: Item) -> _Known:
    known = _Known()
    for claim in item.claims:
        if claim.property == "P31" and claim.qid == "Q5":
            known.is_human = True
        elif claim.property == "P569":
            known.has_birth_date = True
        elif claim.property == "P21":
            known.has_gender = True
        elif claim.property == "P27" and claim.qid is not None:
            known.citizenship_qids.add(claim.qid)
        elif claim.property == "P39" and claim.qid is not None:
            known.position_qids.add(claim.qid)
    for label in item.labels:
        if label.text is not None:
            known.name_texts.add(label.text.casefold())
    for alias in item.aliases:
        if alias.text is not None:
            known.name_texts.add(alias.text.casefold())
    return known


def _wd_lang(lang: Optional[str]) -> str:
    """Map an FtM language (ISO 639-3) to a Wikidata label/alias language code.

    Wikidata keys labels and aliases by mostly-2-letter codes; FtM stores 3-letter
    ones. Untagged or unmappable languages fall back to `mul`, the right home for
    a language-agnostic personal name.
    """
    if lang is None:
        return MULTI_LANG
    return iso_639_alpha2(lang) or MULTI_LANG


def _references(
    entity: StatementEntity,
    retrieved: Optional[str],
    source_url: Optional[str] = None,
) -> List[Snak]:
    """Build the citation snaks for statements derived from this entity.

    Uses the entity's first `sourceUrl` as `S854`, falling back to `source_url`
    (e.g. the dataset's URL when running inside zavod) when the entity carries
    none, plus the optional process-wide `retrieved` date as `S813`. Sourcing is
    best-effort: with no URL at all, an entity still produces commands, but
    unsourced — we warn rather than drop them, since the operator reviews the
    batch before it runs.
    """
    urls = entity.get("sourceUrl", quiet=True)
    url = urls[0] if urls else source_url
    if url is None:
        log.warning("No sourceUrl on %s; emitting unsourced QuickStatements", entity.id)
        return []
    return url_reference(url, retrieved=retrieved)


def _name_statements(entity: StatementEntity) -> List[Tuple[str, str]]:
    """Matchable name-type values as `(text, lang)`, lang defaulting to `mul`.

    We read statements rather than `get()` so each name keeps its language tag.
    Untagged names get `mul` (Wikidata's language-agnostic code), which is the
    right home for romanized/transliterated personal names.
    """
    names: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for stmt in entity.statements:
        prop = entity.schema.get(stmt.prop)
        if prop is None or prop.type != registry.name or not prop.matchable:
            continue
        text = stmt.value
        if text is None or not text.strip():
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append((text, _wd_lang(stmt.lang)))
    return names


def _property_statements(
    entity: StatementEntity,
    target: str,
    known: _Known,
    references: List[Snak],
) -> List[QSCommand]:
    cmds: List[QSCommand] = []
    if not known.is_human:
        cmds.append(AddStatement(target, "P31", QSValue.item("Q5"), references=references))

    if not known.has_birth_date:
        dates = set(entity.get("birthDate", quiet=True))
        if len(dates) == 1:
            value = QSValue.date(dates.pop())
            if value is not None:
                cmds.append(AddStatement(target, "P569", value, references=references))
        elif len(dates) > 1:
            log.warning("Conflicting birthDate on %s; not emitting P569", entity.id)

    if not known.has_gender:
        genders = set(entity.get("gender", quiet=True))
        if len(genders) == 1:
            qid = GENDER_QIDS.get(genders.pop())
            if qid is not None:
                cmds.append(AddStatement(target, "P21", QSValue.item(qid), references=references))
        elif len(genders) > 1:
            log.warning("Conflicting gender on %s; not emitting P21", entity.id)

    # P27 (country of citizenship): pushy — add every citizenship WD lacks — but
    # only present-day sovereign states. `is_country` alone keeps historical ones
    # (USSR passes it), so we also exclude `is_historical`: auto-adding a defunct
    # state's citizenship from screening data is noise, not a useful contribution.
    emitted = set(known.citizenship_qids)
    for code in entity.get("citizenship", quiet=True):
        territory = get_territory(code)
        if territory is None or territory.qid is None:
            continue
        if not territory.is_country or territory.is_historical:
            continue
        if territory.qid in emitted:
            continue
        emitted.add(territory.qid)
        cmds.append(AddStatement(target, "P27", QSValue.item(territory.qid), references=references))
    return cmds


def _position_statements(
    positions: List[PositionClaim],
    target: str,
    known: _Known,
    references: List[Snak],
) -> List[QSCommand]:
    """Emit P39 (position held) for QID-bearing positions Wikidata lacks.

    Conservative by design: a post QID the item already holds is skipped whole
    (no period-merging). A QID seen through a single occupancy carries P580/P582
    date qualifiers; one seen through several (re-election) emits a bare
    statement, so we never imply a continuous tenure across a gap.
    """
    by_qid: Dict[str, List[PositionClaim]] = {}
    for claim in positions:
        if claim.qid in known.position_qids:
            continue
        by_qid.setdefault(claim.qid, []).append(claim)
    cmds: List[QSCommand] = []
    for qid, claims in by_qid.items():
        qualifiers: List[Snak] = []
        if len(claims) == 1:
            start = QSValue.date(claims[0].start) if claims[0].start else None
            if start is not None:
                qualifiers.append(("P580", start))
            end = QSValue.date(claims[0].end) if claims[0].end else None
            if end is not None:
                qualifiers.append(("P582", end))
        value = QSValue.item(qid)
        cmds.append(AddStatement(target, "P39", value, qualifiers, references))
    return cmds


def propose_enrich(
    entity: StatementEntity,
    item: Item,
    retrieved: Optional[str] = None,
    source_url: Optional[str] = None,
    positions: Optional[List[PositionClaim]] = None,
) -> List[QSCommand]:
    """Diff an OS person against a matched Wikidata item into enrichment commands.

    Reach for this once a person is resolved to a QID: it emits QuickStatements
    only for what Wikidata is missing — never a label (which QS would overwrite)
    and never a competing single value. Missing names land as aliases (`Axx`,
    append-only); P31/P569/P21/P27 are added only when absent. `positions` (when
    the caller has resolved the person's QID-bearing positions) become P39
    statements for any post the item doesn't already hold. The result targets the
    item's QID and is safe to run as-is. `source_url` is a fallback citation for
    entities that carry no `sourceUrl` of their own.
    """
    target = item.id
    known = _known_from_item(item)
    references = _references(entity, retrieved, source_url)
    cmds: List[QSCommand] = []
    for text, lang in _name_statements(entity):
        if text.casefold() in known.name_texts:
            continue
        cmds.append(SetAlias(target, lang, text))
    cmds.extend(_property_statements(entity, target, known, references))
    if positions:
        cmds.extend(_position_statements(positions, target, known, references))
    return cmds


def propose_create(
    entity: StatementEntity,
    retrieved: Optional[str] = None,
    source_url: Optional[str] = None,
) -> List[QSCommand]:
    """Compose `CREATE` commands for an OS person with no acceptable Wikidata match.

    Reach for this for the unmatched side of a reconciliation run: it emits a new
    item with the person's primary name as the label, the remaining names as
    aliases, and the same sourced property set as enrichment. QuickStatements
    assigns the new QID asynchronously, so the entity↔QID link is recaptured on a
    later reconciliation pass — there is nothing to read back here. `source_url`
    is a fallback citation for entities that carry no `sourceUrl` of their own.
    """
    references = _references(entity, retrieved, source_url)
    cmds: List[QSCommand] = [CreateItem()]
    names = _name_statements(entity)
    if not names:
        log.warning("No name to create an item for %s", entity.id)
    label_text = entity.caption
    by_text = {text: lang for text, lang in names}
    if label_text not in by_text and names:
        label_text = names[0][0]
    for text, lang in names:
        if text == label_text:
            cmds.append(SetLabel(LAST, lang, text))
        else:
            cmds.append(SetAlias(LAST, lang, text))
    cmds.extend(_property_statements(entity, LAST, _Known(), references))
    return cmds
