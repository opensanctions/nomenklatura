from typing import Set, Tuple
from rigour.ids import get_strong_format_names

from followthemoney import EntityProxy, registry
from nomenklatura.matching.util import has_schema

# HONORARY_STRONG = {registry.phone, registry.email, registry.checksum}
STRONG_FORMATS = get_strong_format_names()


def _get_strong_identifiers(entity: EntityProxy) -> Set[Tuple[str, str]]:
    strong_ids: Set[Tuple[str, str]] = set()
    for prop, value in entity.itervalues():
        if not prop.matchable:
            continue
        if prop.format in STRONG_FORMATS:
            strong_ids.add((prop.format, value))
        # elif prop.type in HONORARY_STRONG:
        #     strong_ids.add((prop.name, value))
    return strong_ids


def _get_weak_identifiers(entity: EntityProxy) -> Set[str]:
    weak_ids: Set[str] = set()
    for prop, value in entity.itervalues():
        if not prop.matchable or not prop.type != registry.identifier:
            continue
        if prop.format in STRONG_FORMATS:
            continue
        weak_ids.add(value)
    return weak_ids


def strong_identifier_match(left: EntityProxy, right: EntityProxy) -> float:
    """Check if two entities share any strong identifiers."""
    # if has_schema(left, right, "Security"):
    #     return 0.0
    left_strong = _get_strong_identifiers(left)
    right_strong = _get_strong_identifiers(right)
    if len(left_strong) == 0 or len(right_strong) == 0:
        return 0.0
    if left_strong.intersection(right_strong):
        return 1.0
    left_nofmt = {v for _, v in left_strong}
    right_nofmt = {v for _, v in right_strong}
    if left_nofmt.intersection(_get_weak_identifiers(right)):
        return 0.7
    if right_nofmt.intersection(_get_weak_identifiers(left)):
        return 0.7
    left_fmts = {f for _, f in left_strong}
    right_fmts = {f for _, f in right_strong}
    common_fmts = left_fmts.intersection(right_fmts)
    return -0.2 * len(common_fmts)


def weak_identifier_match(left: EntityProxy, right: EntityProxy) -> float:
    """Check if two entities share any weak identifiers."""
    if not has_schema(left, right, "LegalEntity"):
        return 0.0
    left_ids = _get_weak_identifiers(left)
    right_ids = _get_weak_identifiers(right)
    if left_ids.intersection(right_ids):
        return 1.0
    # left_formats = {fmt for fmt, _ in left_ids}
    # right_formats = {fmt for fmt, _ in right_ids}
    # if left_formats.intersection(right_formats):
    #     return -0.5
    return 0.0
