from typing import Set
from rigour.names import NameTypeTag, NamePartTag
from rigour.text import levenshtein_similarity
from rigour.names.person import remove_person_prefixes
from followthemoney.proxy import E
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney import model

from nomenklatura.matching.logic_v2.names.symbols import Symbol, SymbolName
from nomenklatura.matching.logic_v2.names.tagging import tag_org_name, tag_person_name
from nomenklatura.matching.logic_v2.names.util import prenormalize_name

PROP_MAPPINGS = (
    ("firstName", NamePartTag.GIVEN),
    ("lastName", NamePartTag.FAMILY),
    ("secondName", NamePartTag.MIDDLE),
    ("middleName", NamePartTag.MIDDLE),
    ("fatherName", NamePartTag.PATRONYMIC),
    ("motherName", NamePartTag.MATRONYMIC),
    ("title", NamePartTag.HONORIFIC),
    ("nameSuffix", NamePartTag.SUFFIX),
    ("weakAlias", NamePartTag.NICK),
)


def schema_type_tag(schema: Schema) -> NameTypeTag:
    if schema.is_a("Person"):
        return NameTypeTag.PER
    elif schema.is_a("Organization"):
        return NameTypeTag.ORG
    elif schema.is_a("LegalEntity"):
        return NameTypeTag.ENT
    elif schema.name in ("Vessel", "Asset", "Airplane", "Security"):
        return NameTypeTag.OBJ
    else:
        return NameTypeTag.UNK


def entity_names(
    type_tag: NameTypeTag, entity: E, is_query: bool = False
) -> Set[SymbolName]:
    names: Set[SymbolName] = set()
    for name in entity.get_type_values(registry.name, matchable=True):
        # Remove prefix like "Mr.", "Ms.", "Dr." from the name:
        if type_tag == NameTypeTag.PER:
            name = remove_person_prefixes(name)

        form = prenormalize_name(name)
        sname = SymbolName(name, form=form, tag=type_tag)
        # tag name parts from properties:
        for prop, tag in PROP_MAPPINGS:
            for value in entity.get(prop, quiet=True):
                sname.tag_text(prenormalize_name(value), tag)

        # TODO: can we guess if something is a company based on org types?

        # tag organization types and symbols:
        if type_tag == NameTypeTag.ORG:
            tag_org_name(sname)

        # tag given name abbreviations. this is meant to handle a case where the person's
        # first or middle name is an abbreviation, e.g. "J. Smith" or "John Q. Smith"
        if type_tag == NameTypeTag.PER:
            for part in sname.parts:
                if is_query and len(part.form) == 1:
                    sym = Symbol(Symbol.Category.PER_ABBR, part.form)
                    sname.apply_part(part, sym)
                elif part.tag in (
                    NamePartTag.GIVEN,
                    NamePartTag.MIDDLE,
                    NamePartTag.PATRONYMIC,
                    NamePartTag.MATRONYMIC,
                ):
                    sym = Symbol(Symbol.Category.PER_ABBR, part.form[0])
                    sname.apply_part(part, sym)
            tag_person_name(sname)

        # TODO: should we tag phonetic names here?
        names.add(sname)
    return names


def match_names(query: SymbolName, result: SymbolName) -> float:
    if query.tag == NameTypeTag.OBJ:
        return levenshtein_similarity(query.form, result.form)
    return levenshtein_similarity(query.form, result.form)


def name_match(query: E, result: E) -> float:
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    if type_tag == NameTypeTag.UNK:
        return 0.0
    query_names = entity_names(type_tag, query, is_query=True)
    result_names = entity_names(type_tag, result)
    best_score = 0.0
    for query_name in query_names:
        for result_name in result_names:
            score = match_names(query_name, result_name)
            if score > best_score:
                best_score = score
    return best_score
