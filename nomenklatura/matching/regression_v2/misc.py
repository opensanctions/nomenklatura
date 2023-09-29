from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.regression_v2.util import tokenize
from nomenklatura.matching.compare.util import has_overlap, extract_numbers
from nomenklatura.matching.util import props_pair, type_pair
from nomenklatura.matching.util import has_schema


def birth_place(left: E, right: E) -> float:
    """Same place of birth."""
    lv, rv = props_pair(left, right, ["birthPlace"])
    lvt = tokenize(lv)
    rvt = tokenize(rv)
    tokens = min(len(lvt), len(rvt))
    return float(len(lvt.intersection(rvt))) / float(max(2.0, tokens))


def address_numbers(left: E, right: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.address)
    lvn = extract_numbers(lv)
    rvn = extract_numbers(rv)
    common = len(lvn.intersection(rvn))
    disjoint = len(lvn.difference(rvn))
    return common - disjoint


def identifier_match(left: E, right: E) -> float:
    """Matching identifiers (e.g. passports, national ID cards, registration or
    tax numbers) between the two entities."""
    if has_schema(left, right, "Organization"):
        return 0.0
    lv, rv = type_pair(left, right, registry.identifier)
    return 1.0 if has_overlap(rv, lv) else 0.0


def org_identifier_match(left: E, right: E) -> float:
    """Matching identifiers (e.g. registration or tax numbers) between two
    organizations or companies."""
    if not has_schema(left, right, "Organization"):
        return 0.0
    lv, rv = type_pair(left, right, registry.identifier)
    return 1.0 if has_overlap(lv, rv) else 0.0
