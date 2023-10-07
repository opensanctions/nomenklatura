from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.regression_v1.util import tokenize_pair, compare_levenshtein
from nomenklatura.matching.compare.util import has_overlap, extract_numbers
from nomenklatura.matching.util import props_pair, type_pair
from nomenklatura.matching.util import compare_sets, has_schema
from nomenklatura.util import normalize_name


def birth_place(query: E, result: E) -> float:
    """Same place of birth."""
    lv, rv = tokenize_pair(props_pair(query, result, ["birthPlace"]))
    tokens = min(len(lv), len(rv))
    return float(len(lv.intersection(rv))) / float(max(2.0, tokens))


def address_match(query: E, result: E) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = [normalize_name(v) for v in lv]
    rvn = [normalize_name(v) for v in rv]
    return compare_sets(lvn, rvn, compare_levenshtein)


def address_numbers(query: E, result: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = extract_numbers(lv)
    rvn = extract_numbers(rv)
    common = len(lvn.intersection(rvn))
    disjoint = len(lvn.difference(rvn))
    return common - disjoint


def phone_match(query: E, result: E) -> float:
    """Matching phone numbers between the two entities."""
    lv, rv = type_pair(query, result, registry.phone)
    return 1.0 if has_overlap(lv, rv) else 0.0


def email_match(query: E, result: E) -> float:
    """Matching email addresses between the two entities."""
    lv, rv = type_pair(query, result, registry.email)
    return 1.0 if has_overlap(lv, rv) else 0.0


def identifier_match(query: E, result: E) -> float:
    """Matching identifiers (e.g. passports, national ID cards, registration or
    tax numbers) between the two entities."""
    if has_schema(query, result, "Organization"):
        return 0.0
    lv, rv = type_pair(query, result, registry.identifier)
    return 1.0 if has_overlap(lv, rv) else 0.0


def org_identifier_match(query: E, result: E) -> float:
    """Matching identifiers (e.g. registration or tax numbers) between two
    organizations or companies."""
    if not has_schema(query, result, "Organization"):
        return 0.0
    lv, rv = type_pair(query, result, registry.identifier)
    return 1.0 if has_overlap(lv, rv) else 0.0
