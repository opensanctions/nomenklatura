from typing import Iterable, List
from normality import WS
from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.util import compare_sets, props_pair, type_pair
from nomenklatura.matching.compare.util import is_disjoint, has_overlap
from nomenklatura.matching.compare.util import compare_levenshtein, extract_numbers
from nomenklatura.matching.compare.names import soundex_name_parts
from nomenklatura.util import fingerprint_name, name_words


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


def name_levenshtein(left: E, right: E) -> float:
    """Levenshtein similiarity between the two entities' names."""
    lv, rv = type_pair(left, right, registry.name)
    lvp = _name_norms(lv)
    rvp = _name_norms(rv)
    return compare_sets(lvp, rvp, compare_levenshtein)


def first_name_match(left: E, right: E) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = props_pair(left, right, ["firstName", "secondName", "middleName"])
    lvt = name_words(lv)
    rvt = name_words(rv)
    return 1.0 if has_overlap(lvt, rvt) else 0.0


def name_part_soundex(left: E, right: E) -> float:
    """Check for overlap of phonetic forms of the names."""
    return soundex_name_parts(left, right)


def name_numbers(left: E, right: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return 1.0 if is_disjoint(extract_numbers(lv), extract_numbers(rv)) else 0.0
