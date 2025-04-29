from typing import Set
from rigour.names import NameTypeTag, NamePartTag
from rigour.names.person import remove_person_prefixes
from followthemoney.proxy import E
from followthemoney.schema import Schema
from followthemoney.types import registry

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
    seen: Set[str] = set()
    names: Set[SymbolName] = set()
    for name in entity.get_type_values(registry.name, matchable=True):
        # Remove prefix like "Mr.", "Ms.", "Dr." from the name:
        if type_tag == NameTypeTag.PER:
            name = remove_person_prefixes(name)

        form = prenormalize_name(name)
        if form in seen:
            continue
        seen.add(form)
        sname = SymbolName(name, form=form, tag=type_tag)
        # tag name parts from properties:
        for prop, tag in PROP_MAPPINGS:
            for value in entity.get(prop, quiet=True):
                sname.tag_text(prenormalize_name(value), tag)

        # tag organization types and symbols:
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            tag_org_name(sname)
            if type_tag == NameTypeTag.ENT:
                # If an entity name contains an organization type, we can tag it as an organization.
                for span in sname.spans:
                    if span.symbol.category == Symbol.Category.ORG_TYPE:
                        sname.tag = NameTypeTag.ORG

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
