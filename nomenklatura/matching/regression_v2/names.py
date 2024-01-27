from typing import Iterable, List, Set
from normality import WS
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.distance import levenshtein

from nomenklatura.matching.util import compare_sets, props_pair, type_pair
from nomenklatura.matching.compare.util import is_disjoint, has_overlap
from nomenklatura.matching.compare.util import extract_numbers
from nomenklatura.util import fingerprint_name, names_word_list, soundex_token


def _name_parts(names: Iterable[str], min_length: int = 1) -> List[List[str]]:
    parts: List[List[str]] = []
    for name in names:
        fp = fingerprint_name(name)
        if fp is not None:
            tokens = [p for p in fp.split(WS) if len(p) >= min_length]
            if len(tokens):
                parts.append(sorted(tokens))
    return parts


def _name_norms(names: Iterable[str]) -> List[str]:
    outs: List[str] = []
    for parts in _name_parts(names):
        outs.append(" ".join(parts))
    return outs


def _compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)


def name_levenshtein(left: E, right: E) -> float:
    """Levenshtein similiarity between the two entities' names."""
    lv, rv = type_pair(left, right, registry.name)
    lvp = _name_norms(lv)
    rvp = _name_norms(rv)
    return compare_sets(lvp, rvp, _compare_levenshtein)


def first_name_match(left: E, right: E) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = props_pair(left, right, ["firstName", "secondName", "middleName"])
    lvt = names_word_list(lv)
    rvt = names_word_list(rv)
    return 1.0 if has_overlap(lvt, rvt) else 0.0


def _name_parts_soundex(names: Iterable[str]) -> List[Set[str]]:
    outs: List[Set[str]] = []
    for parts in _name_parts(names):
        outs.append(set([soundex_token(part) for part in parts]))
    return outs


def name_part_soundex(left: E, right: E) -> float:
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


def name_numbers(left: E, right: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return 1.0 if is_disjoint(extract_numbers(lv), extract_numbers(rv)) else 0.0
