from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair, has_schema
from nomenklatura.util import name_words


def _address_match(query: E, result: E) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = name_words(lv)
    rvn = name_words(rv)
    base = float(max(1, min(len(lvn), len(rvn))))
    # TODO: is this better token-based?
    # return compare_sets(lvn, rvn, compare_levenshtein)
    return len(lvn.intersection(rvn)) / base


def address_entity_match(query: E, result: E) -> float:
    """Two address entities relate to similar addresses."""
    if not has_schema(query, result, "Address"):
        return 0.0
    return _address_match(query, result)


def address_prop_match(query: E, result: E) -> float:
    """Two entities have similar stated addresses."""
    if has_schema(query, result, "Address"):
        return 0.0
    return _address_match(query, result)
