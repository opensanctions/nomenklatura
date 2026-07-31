from itertools import combinations
from normality import WS
from rigour.ids import StrictFormat
from rigour.addresses import normalize_address
from rigour.names import Symbol, NamePartTag
from rigour.names import tokenize_name
from rigour.text import is_stopword
from typing import Generator, Set, Tuple
from followthemoney import registry, StatementEntity
from followthemoney.names import entity_names

WORD_FIELD = "wd"
NAME_PART_FIELD = "np"
PART_PAIR_FIELD = "pp"
SYMBOL_FIELD = "sy"
# Cap the O(k²) growth of part-pair tokens for many-part (mostly org) names:
MAX_PAIR_PARTS = 6
SKIP = (
    # done via entity_names:
    registry.name,
    # registry.country,
    registry.url,
    registry.topic,
    registry.entity,
    registry.number,
    registry.json,
    registry.gender,
    registry.mimetype,
    registry.ip,
    registry.html,
    registry.checksum,
    registry.language,
)
SKIP_PROPERTIES = {
    "wikidataId",
    "wikipediaUrl",
    "publisher",
    "publisherUrl",
    "programId",
    "recordId",
    "legalForm",
    "status",
}
PREFIXES = {
    registry.name: "n",
    registry.identifier: "i",
    registry.country: "c",
    registry.phone: "p",
    registry.address: "a",
    registry.date: "d",
}
EMIT_FULL = (
    registry.country,
    registry.phone,
    registry.email,
)
TEXT_TYPES = (
    registry.text,
    registry.string,
    # registry.address,  # normalized, then added to text type
    registry.identifier,
)


def tokenize_entity(entity: StatementEntity) -> Generator[Tuple[str, str], None, None]:
    unique: Set[Tuple[str, str]] = set()

    # Parsed name parts
    for name in entity_names(
        entity,
        phonetics=False,
        numerics=False,
        consolidate=False,
    ):
        for span in name.spans:
            if span.symbol.category in (
                Symbol.Category.INITIAL,
                Symbol.Category.SYMBOL,
            ):
                continue
            val = f"{SYMBOL_FIELD}:{span.symbol.category.value}:{span.symbol.id}"
            unique.add((SYMBOL_FIELD, val))

        for part in name.parts:
            if part.tag in (NamePartTag.STOP, NamePartTag.LEGAL):
                continue
            if len(part.comparable) < 3 or len(part.comparable) > 30:
                continue
            unique.add((NAME_PART_FIELD, f"{NAME_PART_FIELD}:{part.comparable}"))

        # Part pairs: within-name co-occurrence of two parts. Buckets are far
        # smaller than single-part buckets, so these survive stopwording for
        # common names ("John Smith" ~ "John Q. Smith" share pp:john smith).
        pairable = sorted(
            {
                part.comparable
                for part in name.parts
                if part.tag not in (NamePartTag.STOP, NamePartTag.LEGAL)
                and 2 <= len(part.comparable) <= 30
            }
        )
        if len(pairable) > MAX_PAIR_PARTS:
            # keep the longest parts as the most distinctive ones
            pairable = sorted(sorted(pairable, key=len, reverse=True)[:MAX_PAIR_PARTS])
        for lpart, rpart in combinations(pairable, 2):
            unique.add((PART_PAIR_FIELD, f"{PART_PAIR_FIELD}:{lpart}{WS}{rpart}"))

        if name.comparable:
            name_fp = "".join(sorted({part.comparable for part in name.parts}))
            if len(name_fp) > 3 and len(name_fp) < 200:
                prefix = PREFIXES.get(registry.name, "n")
                unique.add((registry.name.name, f"{prefix}:{name_fp}"))

    for prop, value in entity.itervalues():
        type = prop.type
        if not prop.matchable or type in SKIP or prop.name in SKIP_PROPERTIES:
            continue
        prefix = PREFIXES.get(type, type.name)
        if type in EMIT_FULL:
            full_value = value[:300].lower()
            unique.add((type.name, f"{prefix}:{full_value}"))
            continue
        if type in TEXT_TYPES:
            lvalue = value.lower()
            # min 6 to focus on things that could be fairly unique identifiers
            for token in tokenize_name(lvalue, token_min_length=6):
                if is_stopword(token):
                    continue
                yield WORD_FIELD, f"{WORD_FIELD}:{token}"
        if type == registry.date:
            # if len(value) > 4:
            #     unique.add((type.name, value[:4]))
            unique.add((type.name, f"{prefix}:{value[:10]}"))
            continue
        if type == registry.identifier:
            clean_id = StrictFormat.normalize(value)
            if clean_id is not None:
                unique.add((type.name, f"{prefix}:{clean_id}"))
            continue
        if type == registry.address:
            norm = normalize_address(value)
            if norm is not None:
                # Disable this for now, as it is not performant:
                # norm = remove_address_keywords(norm) or norm
                for word in norm.split(WS):
                    if is_stopword(word):
                        continue
                    if len(word) > 3:
                        yield type.name, f"{prefix}:{word}"
                    if len(word) > 6:
                        yield WORD_FIELD, f"{WORD_FIELD}:{word}"

    yield from unique
