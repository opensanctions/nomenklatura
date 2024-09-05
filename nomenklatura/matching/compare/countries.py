from followthemoney.proxy import E
from followthemoney.types import registry
import numpy as np

from nomenklatura.matching.util import type_pair
from nomenklatura.matching.compare.util import has_overlap, is_disjoint


def country_mismatch(query: E, result: E) -> float:
    """Both entities are linked to different countries."""
    qv, rv = type_pair(query, result, registry.country)
    return 1.0 if is_disjoint(qv, rv) else 0.0


def country_match(query: E, result: E) -> float:
    """Both entities are linked to the same country."""
    qv, rv = type_pair(query, result, registry.country)
    if qv and rv:
        if has_overlap(qv, rv):
            return 1.0
        elif is_disjoint(qv, rv):
            return -1.0  
    return np.nan
