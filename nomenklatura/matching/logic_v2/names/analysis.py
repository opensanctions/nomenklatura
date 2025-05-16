from typing import Set
from rigour.names import NameTypeTag, NamePartTag
from rigour.names.person import remove_person_prefixes
from followthemoney.proxy import E
from followthemoney.schema import Schema
from followthemoney.types import registry

from nomenklatura.matching.logic_v2.names.symbols import Symbol, SymbolName
from nomenklatura.matching.logic_v2.names.tagging import tag_org_name, tag_person_name
from nomenklatura.matching.logic_v2.names.util import prenormalize_name
from nomenklatura.matching.logic_v2.names.util import GIVEN_NAME_TAGS

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


# @lru_cache(maxsize=128)  # Cache the query when doing multiple comparisons
def entity_names(
    type_tag: NameTypeTag, entity: E, is_query: bool = False
) -> Set[SymbolName]:
    """This will transform the entity into a set of names with tags applied. The idea
    is to tag the names with the type of entity they are, e.g. person, organization,
    etc. and to tag the parts of the name with their type, e.g. first name, last name,
    etc. Some extra heuristics and de-duplication are applied to reduce the number of
    comparisons needed to find the best match.
    """
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
                    sym = Symbol(Symbol.Category.PER_INIT, part.form)
                    sname.apply_part(part, sym)
                elif part.tag in GIVEN_NAME_TAGS:
                    sym = Symbol(Symbol.Category.PER_INIT, part.form[0])
                    sname.apply_part(part, sym)
            tag_person_name(sname)

        # TODO: should we tag phonetic names here?
        names.add(sname)

    # Remove short names that are contained in longer names. This is meant to prevent a scenario
    # where a short version of of a name ("John Smith") is matched to a query ("John K Smith"), where
    # a longer version would have disqualified the match ("John K Smith" != "John R Smith").
    for name_obj in list(names):
        for other in names:
            if name_obj == other:
                continue
            if name_obj.contains(other):
                names.remove(other)
    return names
