import itertools
from typing import Set
from rigour.names import NameTypeTag, Name
from rigour.names import replace_org_types_compare, prenormalize_name
from rigour.names import remove_person_prefixes, remove_org_prefixes
from rigour.names import tag_org_name, tag_person_name, normalize_name
from followthemoney import registry, EntityProxy
from followthemoney.names import PROP_PART_TAGS


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
        for prop, tag in PROP_PART_TAGS:
            for value in entity.get(prop, quiet=True):
                sname.tag_text(prenormalize_name(value), tag)

        # tag organization types and symbols:
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            tag_org_name(sname, normalize_name)

        if type_tag == NameTypeTag.PER:
            tag_person_name(sname, normalize_name, any_initials=is_query)

        # TODO: should we tag phonetic tokens here?
        names.add(sname)

    # Remove short names that are contained in longer names. This is meant to prevent a scenario
    # where a short version of of a name ("John Smith") is matched to a query ("John K Smith"), where
    # a longer version would have disqualified the match ("John K Smith" != "John R Smith").
    # We call these super_names because they are (non-strict) supersets of names.
    super_names = set(names)
    for name, other in itertools.combinations(names, 2):
        # Check if name is still in super_names, otherwise two equal names
        # will remove each other with none being left.
        if name in super_names and name.contains(other):
            # Use discard instead of remove here because other may already have been kicked out
            # by another name of which it was a subset.
            super_names.discard(other)
        
    return super_names
