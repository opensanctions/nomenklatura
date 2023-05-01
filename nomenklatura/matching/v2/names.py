from typing import Iterable, Set
from normality import WS
from itertools import combinations
from jellyfish import jaro_winkler_similarity, soundex
from followthemoney.types import registry

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.v1.util import has_disjoint, has_overlap
from nomenklatura.matching.v1.util import compare_sets
from nomenklatura.matching.v1.util import tokenize_pair, props_pair
from nomenklatura.matching.v1.util import type_pair, compare_levenshtein
from nomenklatura.matching.common import extract_numbers
from nomenklatura.util import fingerprint_name


def _normalize_names(raws: Iterable[str]) -> Set[str]:
    names = set()
    for raw in raws:
        name = fingerprint_name(raw)
        if name is not None:
            names.add(name[:128])
    return names


def _name_parts(names: Iterable[str]) -> Set[str]:
    parts: Set[str] = set()
    for name in names:
        fp = fingerprint_name(name)
        if fp is not None:
            parts.update(fp.split(WS))
    return parts


def name_levenshtein(left: Entity, right: Entity) -> float:
    """Consider the edit distance (as a fraction of name length) between the two most
    similar names linked to both entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = _normalize_names(lv), _normalize_names(rv)
    return compare_sets(lvn, rvn, compare_levenshtein)


def first_name_match(left: Entity, right: Entity) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["firstName"]))
    return has_overlap(lv, rv)


def family_name_match(left: Entity, right: Entity) -> float:
    """Matching family name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["lastName"]))
    return has_overlap(lv, rv)


# def name_part_jaro_winkler(left: Entity, right: Entity) -> float:
#     """Check for exact name matches between the two entities."""
#     lv, rv = type_pair(left, right, registry.name)
#     lvn = [_name_parts(n) for n in lv]
#     rvn = [_name_parts(n) for n in rv]
#     best_score = 0.0
#     for lns, rns in combinations(lvn, rvn):
#         pass
#     # lvn, rvn = _name(lv), normalize_names(rv)
#     # common = [len(n) for n in lvn.intersection(rvn)]
#     # max_common = max(common, default=0)
#     # if max_common == 0:
#     #     return 0.0
#     # return float(max_common)
#     return best_score


def name_part_soundex(left: Entity, right: Entity) -> float:
    """Check for exact name matches between the two entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn = [_name_parts(n) for n in lv]
    rvn = [_name_parts(n) for n in rv]
    best_score = 0.0
    for lns, rns in combinations(lvn, rvn):
        pass
    # lvn, rvn = _name(lv), normalize_names(rv)
    # common = [len(n) for n in lvn.intersection(rvn)]
    # max_common = max(common, default=0)
    # if max_common == 0:
    #     return 0.0
    # return float(max_common)
    return best_score


# def name_token_overlap(left: Entity, right: Entity) -> float:
#     """Evaluate the proportion of identical words in each name."""
#     lv, rv = tokenize_pair(type_pair(left, right, registry.name))
#     common = lv.intersection(rv)
#     tokens = min(len(lv), len(rv))
#     return float(len(common)) / float(max(2.0, tokens))


def name_numbers(left: Entity, right: Entity) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return has_disjoint(extract_numbers(lv), extract_numbers(rv))
