from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair
from nomenklatura.matching.compare.util import is_disjoint


def country_mismatch(left: E, right: E) -> float:
    """Both entities are linked to different countries."""
    lv, rv = type_pair(left, right, registry.country)
    return 1.0 if is_disjoint(set(lv), set(rv)) else 0.0
