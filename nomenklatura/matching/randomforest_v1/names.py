from typing import Iterable, Set
from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.regression_v1.util import tokenize_pair, compare_levenshtein
from nomenklatura.matching.compare.util import is_disjoint, has_overlap, extract_numbers
from nomenklatura.matching.util import props_pair, type_pair
from nomenklatura.matching.util import compare_sets
from nomenklatura.util import fingerprint_name


def normalize_names(raws: Iterable[str]) -> Set[str]:
    names = set()
    for raw in raws:
        name = fingerprint_name(raw)
        if name is not None:
            names.add(name[:128])
    return names


def name_levenshtein(left: E, right: E) -> float:
    """Consider the edit distance (as a fraction of name length) between the two most
    similar names linked to both entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = normalize_names(lv), normalize_names(rv)
    return compare_sets(lvn, rvn, compare_levenshtein)


def first_name_match(left: E, right: E) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["firstName"]))
    return 1.0 if has_overlap(lv, rv) else 0.0


def family_name_match(left: E, right: E) -> float:
    """Matching family name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["lastName"]))
    return 1.0 if has_overlap(lv, rv) else 0.0


def name_match(left: E, right: E) -> float:
    """Check for exact name matches between the two entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = normalize_names(lv), normalize_names(rv)
    common = [len(n) for n in lvn.intersection(rvn)]
    max_common = max(common, default=0)
    if max_common == 0:
        return 0.0
    return float(max_common)


def name_token_overlap(left: E, right: E) -> float:
    """Evaluate the proportion of identical words in each name."""
    lv, rv = tokenize_pair(type_pair(left, right, registry.name))
    common = lv.intersection(rv)
    tokens = min(len(lv), len(rv))
    return float(len(common)) / float(max(2.0, tokens))


def name_numbers(left: E, right: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return 1.0 if is_disjoint(extract_numbers(lv), extract_numbers(rv)) else 0.0
