from collections.abc import Generator

from followthemoney import StatementEntity, registry
from followthemoney.names import entity_names
from normality import WS
from rigour.addresses import address_fingerprint
from rigour.ids import StrictFormat
from rigour.names import NamePartTag, Symbol, tokenize_name
from rigour.text import is_stopword

WORD_FIELD = "wd"
NAME_PART_FIELD = "np"
SYMBOL_FIELD = "sy"
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


def tokenize_entity(entity: StatementEntity) -> Generator[tuple[str, str], None, None]:
    unique: set[tuple[str, str]] = set()

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
            addr_fp = address_fingerprint(value)
            if addr_fp is not None:
                for word in addr_fp.split(WS):
                    if is_stopword(word):
                        continue
                    if len(word) > 3:
                        yield type.name, f"{prefix}:{word}"
                    if len(word) > 6:
                        yield WORD_FIELD, f"{WORD_FIELD}:{word}"

    yield from unique
