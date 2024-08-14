from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair
from nomenklatura.matching.compare.util import is_disjoint, has_overlap


def country_mismatch(query: E, result: E) -> float:
    """Both entities are linked to different countries."""
    qv, rv = type_pair(query, result, registry.country)
    return 1.0 if is_disjoint(qv, rv) else 0.0


def country_overlap(query: E, result: E) -> float:
    """Both entities are linked to the same country."""
    qv, rv = type_pair(query, result, registry.country)
    if qv and rv:
        return 1.0 if has_overlap(qv, rv) else 0.0
    else:
        return 0.5
