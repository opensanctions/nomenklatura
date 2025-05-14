from typing import Set

from rigour.ids import get_identifier_format, IdentifierFormat
from followthemoney import model
from followthemoney.property import Property
from followthemoney.types import registry
from followthemoney.proxy import E


def _format_normalize(format: IdentifierFormat, entity: E, prop: Property) -> Set[str]:
    values: Set[str] = set()
    for value in entity.get(prop, quiet=True):
        norm_value = format.normalize(value)
        if norm_value is not None:
            values.add(norm_value)
    return values


def _identifier_format_match(format_name: str, query: E, result: E) -> float:
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
        prop_format = get_identifier_format(prop.format)
        if prop.format is not None and prop_format != format:
            continue
        query_values = _format_normalize(format, query, prop)
        query_identifiers.update(query_values)
        result_values = _format_normalize(format, result, prop)
        result_identifiers.update(result_values)
        if prop.format is not None and prop_format == format:
            query_format.update(query_values)
            result_format.update(result_values)
    if len(query_format.intersection(result_identifiers)) > 0:
        return 1.0
    if len(result_format.intersection(query_identifiers)) > 0:
        return 1.0
    if len(query_identifiers.intersection(result_identifiers)) > 0:
        return 0.8
    return 0.0


def lei_code_match(query: E, result: E) -> float:
    """Two entities have the same Legal Entity Identifier."""
    return _identifier_format_match("lei", query, result)


def bic_code_match(query: E, result: E) -> float:
    """Two entities have the same SWIFT BIC."""
    return _identifier_format_match("bic", query, result)


def ogrn_code_match(query: E, result: E) -> float:
    """Two entities have the same Russian company registration (OGRN) code."""
    return _identifier_format_match("ogrn", query, result)


def inn_code_match(query: E, result: E) -> float:
    """Two entities have the same Russian tax identifier (INN)."""
    return _identifier_format_match("inn", query, result)


def uei_code_match(query: E, result: E) -> float:
    """Two entities have the same US Unique Entity ID (UEI)."""
    return _identifier_format_match("uei", query, result)


def npi_code_match(query: E, result: E) -> float:
    """Two entities have the same US National Provider Identifier (NPI)."""
    return _identifier_format_match("npi", query, result)


def isin_security_match(query: E, result: E) -> float:
    """Two securities have the same ISIN."""
    # if not has_schema(query, result, "Security"):
    #     return 0.0
    return _identifier_format_match("isin", query, result)


def vessel_imo_mmsi_match(query: E, result: E) -> float:
    """Two vessels have the same IMO or MMSI identifier."""
    imo_score = _identifier_format_match("imo", query, result)
    if imo_score > 0.0:
        return imo_score
    query_mmsis = query.get("mmsi", quiet=True)
    result_mmsis = result.get("mmsi", quiet=True)
    return registry.identifier.compare_sets(query_mmsis, result_mmsis)
