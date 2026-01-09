from rigour.territories import territories_intersect
from followthemoney import registry, E

from nomenklatura.matching.util import type_pair, has_schema


# def vessel_country_match(left: E, right: E) -> float:
#     if not has_schema(left, right, "Vessel"):
#         return 0.0
#     lv, rv = type_pair(left, right, registry.country)
#     if len(lv) == 0 or len(rv) == 0:
#         return 0.0
#     common = len(set(lv).intersection(rv))
#     return 1.0 if common > 0 else 0.0


def position_country_match(left: E, right: E) -> float:
    if not has_schema(left, right, "Position"):
        return 0.0
    lv, rv = type_pair(left, right, registry.country)
    if len(lv) == 0 or len(rv) == 0:
        return 0.0
    common = territories_intersect(lv, rv)
    return 1.0 if len(common) > 0 else -1.0


def org_country_mismatch(left: E, right: E) -> float:
    """Check if two entities share a country."""
    if not has_schema(left, right, "LegalEntity") or has_schema(left, right, "Person"):
        return 0.0
    # if not has_schema(left, right, "Organization"):
    #     return 0.0
    lv, rv = type_pair(left, right, registry.country)
    if len(lv) == 0 or len(rv) == 0:
        return 0.0
    common = territories_intersect(lv, rv)
    return 1.0 if len(common) == 0 else 0.0


def per_country_mismatch(left: E, right: E) -> float:
    """ "Check if two persons have distinct countries."""
    if not has_schema(left, right, "Person"):
        return 0.0
    lv, rv = type_pair(left, right, registry.country)
    if len(lv) == 0 or len(rv) == 0:
        return 0.0
    common = territories_intersect(lv, rv)
    return 1.0 if len(common) == 0 else 0.0
