from normality import normalize
from followthemoney.types import registry
from nomenklatura.entity import CompositeEntity as Entity

from nomenklatura.matching.features.util import has_disjoint, has_overlap
from nomenklatura.matching.features.util import compare_levenshtein, compare_sets
from nomenklatura.matching.features.util import props_pair, type_pair, extract_numbers


def birth_place(left: Entity, right: Entity) -> float:
    """Same place of birth."""
    lv, rv = props_pair(left, right, ["birthPlace"])
    lvn = [normalize(v) for v in lv]
    rvn = [normalize(v) for v in rv]
    return compare_sets(lvn, rvn, compare_levenshtein)


def address_match(left: Entity, right: Entity) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(left, right, registry.address)
    lvn = [normalize(v) for v in lv]
    rvn = [normalize(v) for v in rv]
    return compare_sets(lvn, rvn, compare_levenshtein)


def address_numbers(left: Entity, right: Entity) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.address)
    lvn = extract_numbers(lv)
    rvn = extract_numbers(rv)
    common = len(lvn.intersection(rvn))
    disjoint = len(lvn.difference(rvn))
    return common - disjoint


def gender_mismatch(left: Entity, right: Entity) -> float:
    """Both entities have a different gender associated with them."""
    lv, rv = props_pair(left, right, ["gender"])
    return has_disjoint(lv, rv)


def phone_match(left: Entity, right: Entity) -> float:
    """Matching phone numbers between the two entities."""
    lv, rv = type_pair(left, right, registry.phone)
    return has_overlap(set(lv), set(rv))


def email_match(left: Entity, right: Entity) -> float:
    """Matching email addresses between the two entities."""
    lv, rv = type_pair(left, right, registry.email)
    return has_overlap(set(lv), set(rv))


def identifier_match(left: Entity, right: Entity) -> float:
    """Matching identifiers (e.g. passports, national ID cards, registration or
    tax numbers) between the two entities."""
    lv, rv = type_pair(left, right, registry.identifier)
    return has_overlap(set(lv), set(rv))


def country_mismatch(left: Entity, right: Entity) -> float:
    """Both entities are linked to different countries."""
    lv, rv = type_pair(left, right, registry.country)
    return has_disjoint(set(lv), set(rv))
