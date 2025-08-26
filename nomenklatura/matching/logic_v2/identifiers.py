from typing import Set, Type

from rigour.ids import get_identifier_format, IdentifierFormat
from followthemoney import model
from followthemoney.property import Property
from followthemoney.types import registry
from followthemoney.proxy import EntityProxy

from nomenklatura.matching.types import FtResult, ScoringConfig


def _format_normalize(
    format: Type[IdentifierFormat], entity: EntityProxy, prop: Property
) -> Set[str]:
    values: Set[str] = set()
    for value in entity.get(prop, quiet=True):
        norm_value = format.normalize(value)
        if norm_value is not None:
            values.add(norm_value)
    return values


def _identifier_format_match(
    format_name: str, query: EntityProxy, result: EntityProxy
) -> FtResult:
    """Check if the identifier format is the same for two entities."""
    schema = model.common_schema(query.schema, result.schema)
    format = get_identifier_format(format_name)
    query_identifiers: Set[str] = set()
    query_format: Set[str] = set()
    result_identifiers: Set[str] = set()
    result_format: Set[str] = set()
    for prop in schema.properties.values():
        if prop.type != registry.identifier or not prop.matchable:
            continue
        if prop.format is not None and get_identifier_format(prop.format) != format:
            continue
        query_values = _format_normalize(format, query, prop)
        query_identifiers.update(query_values)
        result_values = _format_normalize(format, result, prop)
        result_identifiers.update(result_values)
        if prop.format is not None and get_identifier_format(prop.format) == format:
            query_format.update(query_values)
            result_format.update(result_values)
    left_common = query_format.intersection(result_identifiers)
    if len(left_common) > 0:
        detail = f"Matched {format.TITLE}: {', '.join(left_common)}"
        return FtResult(score=1.0, detail=detail)
    right_common = result_format.intersection(query_identifiers)
    if len(right_common) > 0:
        detail = f"Matched {format.TITLE}: {', '.join(right_common)}"
        return FtResult(score=1.0, detail=detail)
    if format.STRONG:
        non_common = query_identifiers.intersection(result_identifiers)
        if len(non_common) > 0:
            detail = f"Out-of-format match: {', '.join(non_common)}"
            return FtResult(score=0.8, detail=detail)
    return FtResult(score=0.0, detail=f"No {format.TITLE} match")


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
