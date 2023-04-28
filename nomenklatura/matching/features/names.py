from normality import WS
from typing import Iterable, Set
from itertools import combinations
from followthemoney.types import registry

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.features.util import has_disjoint, has_overlap
from nomenklatura.matching.features.util import extract_numbers, compare_sets
from nomenklatura.matching.features.util import props_pair, type_pair
from nomenklatura.matching.features.util import compare_levenshtein
from nomenklatura.util import fingerprint_name, normalize_name


def fingerprint_names(raws: Iterable[str], length: int = 128) -> Set[str]:
    names = set()
    for raw in raws:
        name = fingerprint_name(raw)
        if name is not None:
            names.add(name[:length])
    return names


def name_parts(names: Iterable[str], min_length: int = 0) -> Set[str]:
    """Get a unique set of tokens present in the given set of names."""
    words: Set[str] = set()
    for name in names:
        normalized = normalize_name(name)
        if normalized is not None:
            for word in normalized.split(WS):
                word = word.strip()
                if len(word) > min_length:
                    words.add(word)
    return words


def name_levenshtein(left: Entity, right: Entity) -> float:
    """Consider the edit distance (as a fraction of name length) between the two most
    similar names linked to both entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = fingerprint_names(lv), fingerprint_names(rv)
    return compare_sets(lvn, rvn, compare_levenshtein)


def first_name_match(left: Entity, right: Entity) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = props_pair(left, right, ["firstName"])
    lvp, rvp = name_parts(lv), name_parts(rv)
    return has_overlap(lvp, rvp)


def family_name_match(left: Entity, right: Entity) -> float:
    """Matching family name between the two entities."""
    lv, rv = props_pair(left, right, ["lastName"])
    lvp, rvp = name_parts(lv), name_parts(rv)
    return has_overlap(lvp, rvp)


def name_match(left: Entity, right: Entity) -> float:
    """Check for exact name matches between the two entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = fingerprint_names(lv), fingerprint_names(rv)
    # common = [len(n) for n in lvn.intersection(rvn)]
    # max_common = max(common, default=0)
    # if max_common == 0:
    #     return 0.0
    # return float(max_common)
    return has_overlap(lvn, rvn)


def name_token_overlap(left: Entity, right: Entity) -> float:
    """Evaluate the proportion of identical words in each name."""
    lv, rv = type_pair(left, right, registry.name)
    lvp = name_parts(lv)
    rvp = name_parts(rv)
    common = lvp.intersection(rvp)
    tokens = min(len(lvp), len(rvp))
    return float(len(common)) / float(max(2.0, tokens))


def name_numbers(left: Entity, right: Entity) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return has_disjoint(extract_numbers(lv), extract_numbers(rv))
