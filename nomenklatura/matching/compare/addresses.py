from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import type_pair, has_schema
from nomenklatura.util import names_word_list, list_intersection


def _address_match(query: E, result: E) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(query, result, registry.address)
    lvn = names_word_list(lv)
    rvn = names_word_list(rv)
    base = float(max(1, min(len(lvn), len(rvn))))
    # TODO: is this better token-based?
    return list_intersection(lvn, rvn) / base


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
