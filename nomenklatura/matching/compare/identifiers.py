import re
from typing import Optional
from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair, props_pair, has_schema, compare_sets
from nomenklatura.matching.compare.util import has_overlap, clean_map, CleanFunc
from nomenklatura.util import levenshtein

ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)


def _id_prop_match(
    left: E,
    right: E,
    prop_name: str,
    clean: CleanFunc = None,
) -> bool:
    """Check if a specific property identifier is shared by two entities."""
    prop = left.schema.get(prop_name)
    if prop is None:
        return False
    lv = clean_map(left.get(prop), clean=clean)
    if not len(lv):
        return False
    rv_ = right.get_type_values(prop.type, matchable=True)
    rv = clean_map(rv_, clean=clean)
    common = lv.intersection(rv)
    return len(common) > 0


def _bidi_id_prop_match(
    left: E,
    right: E,
    prop_name: str,
    clean: CleanFunc = None,
) -> float:
    """Check if a specific property identifier is shared by two entities."""
    if _id_prop_match(left, right, prop_name, clean=clean):
        return 1.0
    if _id_prop_match(right, left, prop_name, clean=clean):
        return 1.0
    return 0.0


def _clean_identifier(
    value: str, min_length: int = 6, max_length: int = 100
) -> Optional[str]:
    """Clean up an identifier for comparison."""
    value = ID_CLEAN.sub("", value.upper())
    if len(value) < min_length or len(value) > max_length:
        return None
    return value


def _clean_lei_code(value: str) -> Optional[str]:
    return _clean_identifier(value, min_length=18, max_length=20)


def lei_code_match(left: E, right: E) -> float:
    """Two entities have the same Legal Entity Identifier."""
    return _bidi_id_prop_match(left, right, "leiCode", _clean_lei_code)


def ogrn_code_match(left: E, right: E) -> float:
    """Two entities have the same Russian company registration (OGRN) code."""
    return _bidi_id_prop_match(left, right, "ogrnCode")


def inn_code_match(left: E, right: E) -> float:
    """Two entities have the same Russian tax identifier (INN)."""
    return _bidi_id_prop_match(left, right, "innCode")


def isin_security_match(left: E, right: E) -> float:
    """Two securities have the same ISIN."""
    if not has_schema(left, right, "Security"):
        return 0.0
    return _bidi_id_prop_match(left, right, "isin")


def _clean_imo_number(num: str) -> Optional[str]:
    """Clean up an IMO number for comparison."""
    if num.startswith("IMO"):
        num = num[3:]
    return _clean_identifier(num, min_length=6)


def vessel_imo_mmsi_match(left: E, right: E) -> float:
    """Two vessels have the same IMO or MMSI identifier."""
    imo_score = _bidi_id_prop_match(left, right, "imoNumber", _clean_imo_number)
    if imo_score > 0.0:
        return imo_score
    return _bidi_id_prop_match(left, right, "mmsi")


def crypto_wallet_address(left: E, right: E) -> float:
    """Two cryptocurrency wallets have the same public key."""
    if not has_schema(left, right, "CryptoWallet"):
        return 0.0
    lv, rv = props_pair(left, right, ["publicKey"])
    for key in lv.intersection(rv):
        if len(key) > 10:
            return 1.0
    return 0.0


def orgid_disjoint(left: E, right: E) -> float:
    """Two companies or organizations have different tax identifiers or registration
    numbers."""
    # used by name-qualified
    if not has_schema(left, right, "Organization"):
        return 0.0
    left_ids_, right_ids_ = type_pair(left, right, registry.identifier)
    left_ids = clean_map(left_ids_, _clean_identifier)
    right_ids = clean_map(right_ids_, _clean_identifier)
    if not len(left_ids) or not len(right_ids):
        return 0.0
    if len(left_ids.intersection(right_ids)) > 0:
        return 1.0
    return 1 - compare_sets(left_ids, right_ids, _nq_compare_identifiers)


def identifier_match(left: E, right: E) -> float:
    """Two entities have the same tax or registration identifier."""
    left_ids_, right_ids_ = type_pair(left, right, registry.identifier)
    left_ids = clean_map(left_ids_, _clean_identifier)
    right_ids = clean_map(right_ids_, _clean_identifier)
    return 1.0 if has_overlap(left_ids, right_ids) else 0.0


def _nq_compare_identifiers(left: str, right: str) -> float:
    """Overly clever method for comparing tax and company identifiers."""
    distance = levenshtein(left, right)
    ratio = 1.0 - (distance / float(max(len(left), len(right))))
    return ratio if ratio > 0.7 else 0.0
