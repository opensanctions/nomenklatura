from followthemoney import registry, E

from nomenklatura.matching.util import type_pair, has_schema


# def obj_country(left: E, right: E) -> float:
#     """Check if two entities share a country."""
#     if has_schema(left, right, "LegalEntity"):
#         return 0.0
#     lv, rv = type_pair(left, right, registry.country)
#     if len(lv) == 0 or len(rv) == 0:
#         return 0.0
#     common = len(set(lv).intersection(rv))
#     return 1.0 if common > 0 else -1.0
#     # if common == 0:
#     #     return -1.0
#     # total = len(lv) + len(rv)
#     # return float(common) / total


def org_obj_country_match(left: E, right: E) -> float:
    """Check if two entities share a country."""
    if has_schema(left, right, "LegalEntity") and not has_schema(
        left, right, "Organization"
    ):
        return 0.0
    if has_schema(left, right, "Position"):
        return 0.0
    lv, rv = type_pair(left, right, registry.country)
    if len(lv) == 0 or len(rv) == 0:
        return 0.0
    common = len(set(lv).intersection(rv))
    return 1.0 if common > 0 else -1.0


def per_country_mismatch(left: E, right: E) -> float:
    """Both persons are linked to different countries."""
    if not has_schema(left, right, "Person"):
        return 0.0
    qv, rv = type_pair(left, right, registry.country)
    if len(qv) == 0 or len(rv) == 0:
        return 0.0
    overlap = len(set(qv).intersection(rv))
    return 1.0 if overlap == 0 else -0.2


def pos_country_mismatch(query: E, result: E) -> float:
    """Whether positions have the same country or not"""
    if not has_schema(query, result, "Position"):
        return 0.0
    lv, rv = type_pair(query, result, registry.country)
    if len(lv) == 0 or len(rv) == 0:
        return 0.0
    if set(lv).intersection(rv):
        return 0.0
    return 1.0
