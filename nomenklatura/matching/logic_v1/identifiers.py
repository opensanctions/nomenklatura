from rigour.ids import LEI, ISIN, INN, OGRN, IMO, BIC
from followthemoney.proxy import E

from nomenklatura.matching.util import has_schema
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
