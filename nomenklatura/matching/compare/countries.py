from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import type_pair


def country_mismatch(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Both entities are linked to different countries."""
    qv, rv = type_pair(query, result, registry.country)
    if len(qv) > 0 and len(rv) > 0:
        if len(set(qv).intersection(rv)) == 0:
            detail = f"Different countries: {qv} / {rv}"
            return FtResult(score=1.0, detail=detail)
    return FtResult(score=0.0, detail=None)
