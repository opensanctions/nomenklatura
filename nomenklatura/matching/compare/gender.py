from followthemoney.proxy import E

from nomenklatura.matching.util import props_pair
from nomenklatura.matching.compare.util import is_disjoint


def gender_mismatch(left: E, right: E) -> float:
    """Both entities have a different gender associated with them."""
    lv, rv = props_pair(left, right, ["gender"])
    return 1.0 if is_disjoint(set(lv), set(rv)) else 0.0
