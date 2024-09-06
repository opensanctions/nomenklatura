from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair
from nomenklatura.matching.compare.util import is_disjoint


def country_match(query: E, result: E) -> float:
    """Both entities are linked to the same country."""
    qv, rv = type_pair(query, result, registry.country)
    if qv and rv:
        if has_overlap(qv, rv):
            return 1.0
        elif is_disjoint(qv, rv):
            return -1.0
    return 0.0
