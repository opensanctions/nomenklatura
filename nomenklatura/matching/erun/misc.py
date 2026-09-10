from followthemoney import E, registry
from rigour.addresses import address_fingerprint

from nomenklatura.matching.compare.util import extract_numbers
from nomenklatura.matching.util import has_schema, type_pair

OTHER = registry.gender.OTHER


def _place_tokens(places: list[str]) -> set[str]:
    tokens: set[str] = set()
    for place in places:
        fingerprint = address_fingerprint(place)
        if fingerprint is not None:
            tokens.update(fingerprint.split())
    return tokens


def birth_place(query: E, result: E) -> float:
    """Same place of birth."""
    if not has_schema(query, result, "Person"):
        return 0.0
    lparts = _place_tokens(query.get("birthPlace", quiet=True))
    rparts = _place_tokens(result.get("birthPlace", quiet=True))
    overlap = len(lparts.intersection(rparts))
    base_length = max(1.0, min(len(lparts), len(rparts)))
    return overlap / base_length


def _address_number_sets(query: E, result: E) -> tuple[set[str], set[str]]:
    lv, rv = type_pair(query, result, registry.address)
    return extract_numbers(lv), extract_numbers(rv)


def address_number_overlap(query: E, result: E) -> float:
    """Measure shared address numbers without rewarding repeated addresses."""

    left, right = _address_number_sets(query, result)
    if not left or not right:
        return 0.0
    common = len(left.intersection(right))
    return common / min(len(left), len(right))


def address_number_disagreement(query: E, result: E) -> float:
    """Bound conflicting address numbers so address history cannot dominate a match."""

    left, right = _address_number_sets(query, result)
    if not left or not right:
        return 0.0
    difference = len(left.symmetric_difference(right))
    return difference / len(left.union(right))


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
    phones = registry.phone.compare_sets(lv, rv)
    if phones > 0:
        return phones
    lv, rv = type_pair(query, result, registry.email)
    emails = registry.email.compare_sets(lv, rv)
    if emails > 0:
        return emails
    lv, rv = type_pair(query, result, registry.url)
    urls = registry.url.compare_sets(lv, rv)
    if urls > 0:
        return urls
    return 0.0


def security_isin_mismatch(query: E, result: E) -> float:
    """Compare ISIN codes for Security entities."""
    if not has_schema(query, result, "Security"):
        return 0.0
    query_isins = set(query.get("isin", quiet=True))
    result_isins = set(result.get("isin", quiet=True))
    if len(query_isins) == 0 or len(result_isins) == 0:
        return 0.0
    if query_isins.intersection(result_isins):
        return 0.0
    return 1.0
