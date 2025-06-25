from typing import Set
from rigour.names import NameTypeTag, NamePartTag, Name
from rigour.names import replace_org_types_compare, prenormalize_name
from rigour.names import remove_person_prefixes, remove_org_prefixes
from rigour.names import tag_org_name, tag_person_name
from followthemoney.proxy import EntityProxy
from followthemoney.schema import Schema
from followthemoney.types import registry

from nomenklatura.matching.logic_v2.names.util import normalize_name

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
    type_tag: NameTypeTag, entity: EntityProxy, is_query: bool = False
) -> Set[Name]:
    """This will transform the entity into a set of names with tags applied. The idea
    is to tag the names with the type of entity they are, e.g. person, organization,
    etc. and to tag the parts of the name with their type, e.g. first name, last name,
    etc. Some extra heuristics and de-duplication are applied to reduce the number of
    comparisons needed to find the best match.
    """
    seen: Set[str] = set()
    names: Set[Name] = set()
    for name in entity.get_type_values(registry.name, matchable=True):
        # Remove prefix like "Mr.", "Ms.", "Dr." from the name:
        if type_tag == NameTypeTag.PER:
            name = remove_person_prefixes(name)

        form = prenormalize_name(name)
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            # Replace organization types with their canonical form, e.g. "Limited Liability Company" -> "LLC"
            form = replace_org_types_compare(form, normalizer=prenormalize_name)
            # Remove organization prefixes like "The" (actually that's it right now)
            form = remove_org_prefixes(form)

        if form in seen:
            continue
        seen.add(form)
        sname = Name(name, form=form, tag=type_tag)
        # tag name parts from properties:
        for prop, tag in PROP_MAPPINGS:
            for value in entity.get(prop, quiet=True):
                sname.tag_text(prenormalize_name(value), tag)

        # tag organization types and symbols:
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            tag_org_name(sname, normalize_name)

        if type_tag == NameTypeTag.PER:
            tag_person_name(sname, normalize_name, any_initials=is_query)

        # TODO: should we tag phonetic names here?
        names.add(sname)

    # Remove short names that are contained in longer names. This is meant to prevent a scenario
    # where a short version of of a name ("John Smith") is matched to a query ("John K Smith"), where
    # a longer version would have disqualified the match ("John K Smith" != "John R Smith").
    for name_obj in list(names):
        for other in list(names):
            if name_obj.contains(other):
                names.remove(other)
    return names
