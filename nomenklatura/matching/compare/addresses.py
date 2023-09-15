from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.compare.util import clean_map, compare_levenshtein
from nomenklatura.matching.util import type_pair, has_schema, compare_sets
from nomenklatura.util import normalize_name, name_words


def _address_match(left: E, right: E) -> float:
    """Text similarity between addresses."""
    lv, rv = type_pair(left, right, registry.address)
    lvn = name_words(lv)
    rvn = name_words(rv)
    base = float(max(1, min(len(lvn), len(rvn))))
    # TODO: is this better token-based?
    # return compare_sets(lvn, rvn, compare_levenshtein)
    return len(lvn.intersection(rvn)) / base


def address_entity_match(left: E, right: E) -> float:
    """Two address entities relate to similar addresses."""
    if not has_schema(left, right, "Address"):
        return 0.0
    return _address_match(left, right)


def address_prop_match(left: E, right: E) -> float:
    """Two entities have similar stated addresses."""
    if has_schema(left, right, "Address"):
        return 0.0
    return _address_match(left, right)
