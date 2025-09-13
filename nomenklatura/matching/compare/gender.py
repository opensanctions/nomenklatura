from followthemoney.proxy import E

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import props_pair
from nomenklatura.matching.util import FNUL


def gender_mismatch(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Both entities have a different gender associated with them."""
    qv, rv = props_pair(query, result, ["gender"])
    if len(qv) > 0 and len(rv) > 0:
        if len(set(qv).intersection(rv)) == 0:
            detail = f"Different genders: {qv} / {rv}"
            return FtResult(score=1.0, detail=detail)
    return FtResult(score=FNUL, detail=None)
