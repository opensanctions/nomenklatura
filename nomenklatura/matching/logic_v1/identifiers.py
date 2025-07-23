from itertools import product
from rigour.ids import LEI, ISIN, INN, OGRN, IMO, BIC
from rigour.ids import StrictFormat
from rigour.text.distance import levenshtein
from followthemoney import E, registry

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import has_schema, type_pair
from nomenklatura.matching.compare.util import clean_map, CleanFunc


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
) -> FtResult:
    """Check if a specific property identifier is shared by two entities."""
    if _id_prop_match(query, result, prop_name, clean=clean):
        return FtResult(score=1.0, detail="Property match: %r" % prop_name)
    if _id_prop_match(result, query, prop_name, clean=clean):
        return FtResult(score=1.0, detail="Property match: %r" % prop_name)
    return FtResult(score=0.0, detail="No match: %r" % prop_name)


def lei_code_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have the same Legal Entity Identifier."""
    return _bidi_id_prop_match(query, result, "leiCode", LEI.normalize)


def bic_code_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have the same SWIFT BIC."""
    return _bidi_id_prop_match(query, result, "swiftBic", BIC.normalize)


def ogrn_code_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have the same Russian company registration (OGRN) code."""
    return _bidi_id_prop_match(query, result, "ogrnCode", OGRN.normalize)


def inn_code_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have the same Russian tax identifier (INN)."""
    return _bidi_id_prop_match(query, result, "innCode", INN.normalize)


def isin_security_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two securities have the same ISIN."""
    if not has_schema(query, result, "Security"):
        return FtResult(score=0.0, detail="None of the entities is a security")
    return _bidi_id_prop_match(query, result, "isin", ISIN.normalize)


def vessel_imo_mmsi_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two vessels have the same IMO or MMSI identifier."""
    imo_res = _bidi_id_prop_match(query, result, "imoNumber", IMO.normalize)
    if imo_res.score > 0.0:
        return imo_res
    return _bidi_id_prop_match(query, result, "mmsi")


def orgid_disjoint(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two companies or organizations have different tax identifiers or registration
    numbers."""
    if not has_schema(query, result, "Organization"):
        return FtResult(score=0.0, detail=None)
    query_ids_, result_ids_ = type_pair(query, result, registry.identifier)
    query_ids = clean_map(query_ids_, StrictFormat.normalize)
    result_ids = clean_map(result_ids_, StrictFormat.normalize)
    if not len(query_ids) or not len(result_ids):
        return FtResult(score=0.0, detail=None)
    common = query_ids.intersection(result_ids)
    if len(common) > 0:
        return FtResult(score=0.0, detail=None)
    max_ratio = 0.0
    for query_id, result_id in product(query_ids, result_ids):
        distance = levenshtein(query_id, result_id)
        max_len = max(len(query_id), len(result_id))
        ratio = 1.0 - (distance / float(max_len))
        if ratio > 0.7:
            max_ratio = max(max_ratio, ratio)
    detail = "Mismatched identifiers: %s vs %s" % (
        ", ".join(query_ids),
        ", ".join(result_ids),
    )
    return FtResult(score=1 - max_ratio, detail=detail)
