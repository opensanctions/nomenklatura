from typing import List, Optional, Set
from followthemoney import registry, E

from nomenklatura.matching.compare.util import extract_numbers
from nomenklatura.matching.util import type_pair
from nomenklatura.matching.util import has_schema

from rigour.addresses import normalize_address, shorten_address_keywords

OTHER = registry.gender.OTHER


def _norm_address(addr: str, latinize: bool = True) -> Optional[str]:
    norm_addr = normalize_address(addr, latinize=latinize, min_length=4)
    if norm_addr is not None:
        norm_addr = shorten_address_keywords(norm_addr, latinize=latinize)
    return norm_addr


def _norm_place(places: List[str]) -> Set[str]:
    parts = set()
    for place in places:
        norm_place = _norm_address(place)
        if norm_place is not None:
            for part in norm_place.split(" "):
                parts.add(part)
    return parts


def birth_place(query: E, result: E) -> float:
    """Same place of birth."""
    if not has_schema(query, result, "Person"):
        return 0.0
    lparts = _norm_place(query.get("birthPlace", quiet=True))
    rparts = _norm_place(result.get("birthPlace", quiet=True))
    overlap = len(lparts.intersection(rparts))
    base_length = max(1.0, min(len(lparts), len(rparts)))
    return overlap / base_length


def address_match(query: E, result: E) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = _norm_place(lv)
    rvn = _norm_place(rv)
    if len(lvn) == 0 or len(rvn) == 0:
        return 0.0
    overlap = len(lvn.intersection(rvn))
    tokens = max(1.0, min(len(lvn), len(rvn)))
    if overlap == 0:
        return 0.0
    return float(overlap) / float(tokens)


def address_numbers(query: E, result: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = extract_numbers(lv)
    rvn = extract_numbers(rv)
    common = len(lvn.intersection(rvn))
    disjoint = len(lvn.difference(rvn))
    return common - disjoint


def gender_mismatch(query: E, result: E) -> float:
    """Both entities have a different gender associated with them."""
    qv = {v for v in query.get("gender", quiet=True) if v != OTHER}
    rv = {v for v in result.get("gender", quiet=True) if v != OTHER}
    if len(qv) == 1 and len(rv) == 1 and len(qv.intersection(rv)) == 0:
        return 1.0
    return 0.0


def contact_match(query: E, result: E) -> float:
    """Matching contact information between the two entities."""
    lv, rv = type_pair(query, result, registry.phone)
    if set(lv).intersection(set(rv)):
        return 1.0
    lv, rv = type_pair(query, result, registry.email)
    if set(lv).intersection(set(rv)):
        return 1.0
    lv, rv = type_pair(query, result, registry.url)
    if set(lv).intersection(set(rv)):
        return 1.0
    return 0.0


def security_isin_match(query: E, result: E) -> float:
    """Both entities are linked to different ISIN codes."""
    if not has_schema(query, result, "Security"):
        return 0.0
    query_isins = set(query.get("isin", quiet=True))
    result_isins = set(result.get("isin", quiet=True))
    if len(query_isins) == 0 or len(result_isins) == 0:
        return 0.0
    if query_isins.intersection(result_isins):
        return 1.0
    return -2.0
