from rigour.ids import LEI, ISIN, INN, OGRN, IMO, BIC, StrictFormat
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.distance import levenshtein

from nomenklatura.matching.util import type_pair, props_pair, has_schema, compare_sets
from nomenklatura.matching.compare.util import has_overlap, clean_map, CleanFunc


def _id_prop_match(
    query: E,
    result: E,
    prop_name: str,
    clean: CleanFunc = None,
) -> bool:
    """Check if a specific property identifier is shared by two entities."""
    prop = query.schema.get(prop_name)
    if prop is None:
        return False
    lv = clean_map(query.get(prop), clean=clean)
    if not len(lv):
        return False
    rv_ = result.get_type_values(prop.type, matchable=True)
    rv = clean_map(rv_, clean=clean)
    common = lv.intersection(rv)
    return len(common) > 0


def _bidi_id_prop_match(
    query: E,
    result: E,
    prop_name: str,
    clean: CleanFunc = None,
) -> float:
    """Check if a specific property identifier is shared by two entities."""
    if _id_prop_match(query, result, prop_name, clean=clean):
        return 1.0
    if _id_prop_match(result, query, prop_name, clean=clean):
        return 1.0
    return 0.0


def lei_code_match(query: E, result: E) -> float:
    """Two entities have the same Legal Entity Identifier."""
    return _bidi_id_prop_match(query, result, "leiCode", LEI.normalize)


def bic_code_match(query: E, result: E) -> float:
    """Two entities have the same SWIFT BIC."""
    return _bidi_id_prop_match(query, result, "swiftBic", BIC.normalize)


def ogrn_code_match(query: E, result: E) -> float:
    """Two entities have the same Russian company registration (OGRN) code."""
    return _bidi_id_prop_match(query, result, "ogrnCode", OGRN.normalize)


def inn_code_match(query: E, result: E) -> float:
    """Two entities have the same Russian tax identifier (INN)."""
    return _bidi_id_prop_match(query, result, "innCode", INN.normalize)


def isin_security_match(query: E, result: E) -> float:
    """Two securities have the same ISIN."""
    if not has_schema(query, result, "Security"):
        return 0.0
    return _bidi_id_prop_match(query, result, "isin", ISIN.normalize)


def vessel_imo_mmsi_match(query: E, result: E) -> float:
    """Two vessels have the same IMO or MMSI identifier."""
    imo_score = _bidi_id_prop_match(query, result, "imoNumber", IMO.normalize)
    if imo_score > 0.0:
        return imo_score
    return _bidi_id_prop_match(query, result, "mmsi")


def crypto_wallet_address(query: E, result: E) -> float:
    """Two cryptocurrency wallets have the same public key."""
    if not has_schema(query, result, "CryptoWallet"):
        return 0.0
    lv, rv = props_pair(query, result, ["publicKey"])
    for key in lv.intersection(rv):
        if len(key) > 10:
            return 1.0
    return 0.0


def orgid_disjoint(query: E, result: E) -> float:
    """Two companies or organizations have different tax identifiers or registration
    numbers."""
    # used by name-qualified
    if not has_schema(query, result, "Organization"):
        return 0.0
    query_ids_, result_ids_ = type_pair(query, result, registry.identifier)
    query_ids = clean_map(query_ids_, StrictFormat.normalize)
    result_ids = clean_map(result_ids_, StrictFormat.normalize)
    if not len(query_ids) or not len(result_ids):
        return 0.0
    if len(query_ids.intersection(result_ids)) > 0:
        return 0.0
    return 1 - compare_sets(query_ids, result_ids, _nq_compare_identifiers)


def identifier_match(query: E, result: E) -> float:
    """Two entities have the same tax or registration identifier."""
    query_ids_, result_ids_ = type_pair(query, result, registry.identifier)
    query_ids = clean_map(query_ids_, StrictFormat.normalize)
    result_ids = clean_map(result_ids_, StrictFormat.normalize)
    return 1.0 if has_overlap(query_ids, result_ids) else 0.0


def _nq_compare_identifiers(query: str, result: str) -> float:
    """Overly clever method for comparing tax and company identifiers."""
    distance = levenshtein(query, result)
    ratio = 1.0 - (distance / float(max(len(query), len(result))))
    return ratio if ratio > 0.7 else 0.0
