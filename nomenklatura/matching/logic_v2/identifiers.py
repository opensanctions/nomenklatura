from typing import Optional, Set

from rigour.ids import get_identifier_format
from followthemoney.types import registry
from followthemoney.proxy import EntityProxy

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import FNUL


def format_values(entity: EntityProxy, format_name: Optional[str]) -> Set[str]:
    """Get all identifier values of a given format from an entity."""
    values: Set[str] = set()
    for prop in entity.iterprops():
        if prop.type != registry.identifier or not prop.matchable:
            continue
        if prop.format == format_name:
            values.update(entity.get(prop))
    return values


def _identifier_format_match(
    format_name: str, query: EntityProxy, result: EntityProxy
) -> FtResult:
    """Check if the identifier format is the same for two entities."""
    format = get_identifier_format(format_name)
    if format is None:
        raise RuntimeError(f"Unknown identifier format: {format_name}")
    query_format = format_values(query, format_name)
    result_format = format_values(result, format_name)
    if len(query_format) == 0 and len(result_format) == 0:
        return FtResult(score=FNUL, detail=f"No {format.TITLE} match")
    common = query_format.intersection(result_format)
    if len(common) > 0:
        detail = f"Matched {format.TITLE}: {', '.join(common)}"
        return FtResult(score=1.0, detail=detail)
    if len(query_format) > 0:
        result_generic = [format.normalize(f) for f in format_values(result, None)]
        if len(set(query_format).intersection(result_generic)) > 0:
            detail = f"Matched {format.TITLE}: {', '.join(common)}"
            return FtResult(score=1.0, detail=detail)
    if len(result_format) > 0:
        query_generic = [format.normalize(f) for f in format_values(query, None)]
        if len(set(result_format).intersection(query_generic)) > 0:
            detail = f"Matched {format.TITLE}: {', '.join(common)}"
            return FtResult(score=1.0, detail=detail)
    return FtResult(score=FNUL, detail=f"No {format.TITLE} match")


def lei_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same Legal Entity Identifier."""
    return _identifier_format_match("lei", query, result)


def bic_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same SWIFT BIC."""
    return _identifier_format_match("bic", query, result)


def ogrn_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same Russian company registration (OGRN) code."""
    return _identifier_format_match("ogrn", query, result)


def inn_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same Russian tax identifier (INN)."""
    return _identifier_format_match("inn", query, result)


def uei_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same US Unique Entity ID (UEI)."""
    return _identifier_format_match("uei", query, result)


def npi_code_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two entities have the same US National Provider Identifier (NPI)."""
    return _identifier_format_match("npi", query, result)


def isin_security_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two securities have the same ISIN."""
    # if not has_schema(query, result, "Security"):
    #     return 0.0
    return _identifier_format_match("isin", query, result)


def vessel_imo_mmsi_match(
    query: EntityProxy, result: EntityProxy, config: ScoringConfig
) -> FtResult:
    """Two vessels have the same IMO or MMSI identifier."""
    imo_res = _identifier_format_match("imo", query, result)
    if imo_res.score > 0.0:
        return imo_res
    query_mmsis = query.get("mmsi", quiet=True)
    result_mmsis = result.get("mmsi", quiet=True)
    score = registry.identifier.compare_sets(query_mmsis, result_mmsis)
    if score > 0.0:
        return FtResult(score=score, detail="MMSI match")
    return FtResult(score=score, detail="No IMO or MMSI match")
