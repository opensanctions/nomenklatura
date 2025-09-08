from rigour.ids import StrictFormat
from followthemoney import E, registry

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import type_pair, props_pair, has_schema
from nomenklatura.matching.compare.util import clean_map
from nomenklatura.matching.util import FNUL


def crypto_wallet_address(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two cryptocurrency wallets have the same public key."""
    if not has_schema(query, result, "CryptoWallet"):
        return FtResult(score=FNUL, detail=None)
    lv, rv = props_pair(query, result, ["publicKey"])
    for key in lv.intersection(rv):
        if len(key) > 10:
            return FtResult(score=1.0, detail="Matched address: %s" % key)
    return FtResult(score=FNUL, detail=None)


def identifier_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have the same tax or registration identifier."""
    query_ids_, result_ids_ = type_pair(query, result, registry.identifier)
    query_ids = clean_map(query_ids_, StrictFormat.normalize)
    result_ids = clean_map(result_ids_, StrictFormat.normalize)
    common = query_ids.intersection(result_ids)
    if len(common) > 0:
        detail = "Matched identifiers: %s" % ", ".join(common)
        return FtResult(score=1.0, detail=detail)
    return FtResult(score=FNUL, detail=None)
