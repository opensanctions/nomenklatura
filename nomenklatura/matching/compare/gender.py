from followthemoney.proxy import E

from nomenklatura.matching.util import props_pair
from nomenklatura.matching.compare.util import is_disjoint


def gender_mismatch(query: E, result: E) -> float:
    """Both entities have a different gender associated with them."""
    qv, rv = props_pair(query, result, ["gender"])
    return 1.0 if is_disjoint(qv, rv) else 0.0
