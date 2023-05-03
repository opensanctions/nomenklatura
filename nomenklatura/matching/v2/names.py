import statistics
import Levenshtein
from typing import Iterable, Set, List
from normality import WS
from itertools import combinations
from jellyfish import jaro_winkler_similarity, soundex
from followthemoney.types import registry

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.v2.util import has_disjoint, has_overlap
from nomenklatura.matching.v2.util import compare_sets, props_pair
from nomenklatura.matching.v2.util import type_pair, tokenize  #  , compare_levenshtein
from nomenklatura.matching.common import extract_numbers
from nomenklatura.util import fingerprint_name


def _name_parts(names: Iterable[str], min_length: int = 1) -> List[List[str]]:
    parts: List[List[str]] = []
    for name in names:
        fp = fingerprint_name(name)
        if fp is not None:
            tokens = [p for p in fp.split(WS) if len(p) >= min_length]
            if len(tokens):
                parts.append(sorted(tokens))
    return parts


def _name_parts_soundex(names: Iterable[str]) -> List[Set[str]]:
    outs: List[Set[str]] = []
    for parts in _name_parts(names):
        outs.append(set([soundex(part) for part in parts]))
    return outs


def _name_norms(names: Iterable[str]) -> List[str]:
    outs: List[str] = []
    for parts in _name_parts(names):
        outs.append(" ".join(parts))
    return outs


# def _jaro_parts(lefts: List[str], rights: List[str]) -> float:
#     pass


def _compare_levenshtein(left: str, right: str) -> float:
    distance = Levenshtein.distance(left, right)
    base = max((15, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)


def name_levenshtein(left: Entity, right: Entity) -> float:
    lv, rv = type_pair(left, right, registry.name)
    lvp = _name_norms(lv)
    rvp = _name_norms(rv)
    # print("NORMS", lvp, rvp)
    # return compare_sets(lvp, rvp, jaro_winkler_similarity, select_func=statistics.mean)
    return compare_sets(lvp, rvp, _compare_levenshtein)


def first_name_match(left: Entity, right: Entity) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = props_pair(left, right, ["firstName", "secondName", "middleName"])
    lvt = tokenize(lv)
    rvt = tokenize(rv)
    return has_overlap(lvt, rvt)


def family_name_match(left: Entity, right: Entity) -> float:
    """Matching family name between the two entities."""
    lv, rv = props_pair(left, right, ["lastName"])
    lvt = tokenize(lv)
    rvt = tokenize(rv)
    return has_overlap(lvt, rvt)


def name_part_soundex(left: Entity, right: Entity) -> float:
    """Check for overlap of phonetic forms of the names."""
    lv, rv = type_pair(left, right, registry.name)
    rvn = _name_parts_soundex(rv)
    best_score = 0.0
    for lns in _name_parts_soundex(lv):
        if not len(lns):
            continue
        for rns in rvn:
            if not len(rns):
                continue
            overlap = len(lns.intersection(rns))
            score = float(overlap) / float(min(len(lns), len(rns)))
            best_score = max(best_score, score)
        if best_score == 1.0:
            return best_score
    return best_score


def name_numbers(left: Entity, right: Entity) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return has_disjoint(extract_numbers(lv), extract_numbers(rv))
