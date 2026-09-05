from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.addresses import match_addresses

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import FNUL, has_schema


def _address_match(query: E, result: E) -> FtResult:
    """Text similarity between addresses."""
    query_addrs = query.get_type_values(registry.address, matchable=True)
    result_addrs = result.get_type_values(registry.address, matchable=True)
    match = match_addresses(query_addrs, result_addrs)
    if match is None:
        return FtResult(score=FNUL, detail=None)
    return FtResult(
        match.score,
        detail=match.detail,
        query=match.query,
        candidate=match.result,
    )


def address_entity_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two address entities relate to similar addresses."""
    if not has_schema(query, result, "Address"):
        return FtResult(score=FNUL, detail=None)
    return _address_match(query, result)


def address_prop_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have similar stated addresses."""
    if has_schema(query, result, "Address"):
        return FtResult(score=FNUL, detail=None)
    return _address_match(query, result)
