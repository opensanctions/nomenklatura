import math
import fingerprints
from typing import Iterable, Set
from followthemoney.types import registry

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.features.util import has_disjoint, has_overlap, has_schema
from nomenklatura.matching.features.util import extract_numbers, compare_sets
from nomenklatura.matching.features.util import tokenize_pair, props_pair
from nomenklatura.matching.features.util import type_pair, compare_levenshtein


def normalize_names(raws: Iterable[str]) -> Set[str]:
    names = set()
    for raw in raws:
        name = fingerprints.generate(raw)
        if name is None:
            continue
        names.add(name[:128])
    return names


def name_levenshtein(left: Entity, right: Entity) -> float:
    """Consider the edit distance (as a fraction of name length) between the two most
    similar names linked to both entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = normalize_names(lv), normalize_names(rv)
    return compare_sets(lvn, rvn, compare_levenshtein)


def first_name_match(left: Entity, right: Entity) -> float:
    """Matching first/given name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["firstName"]))
    return has_overlap(lv, rv)


def family_name_match(left: Entity, right: Entity) -> float:
    """Matching family name between the two entities."""
    lv, rv = tokenize_pair(props_pair(left, right, ["lastName"]))
    return has_overlap(lv, rv)


def name_match(left: Entity, right: Entity) -> float:
    """Check for exact name matches between the two entities."""
    lv, rv = type_pair(left, right, registry.name)
    lvn, rvn = normalize_names(lv), normalize_names(rv)
    common = [len(n) for n in lvn.intersection(rvn)]
    max_common = max(common, default=0)
    if max_common == 0:
        return 0.0
    return math.log(float(max_common))
    # return has_intersection(lvn, rvn)


def name_token_overlap(left: Entity, right: Entity) -> float:
    """Evaluate the proportion of identical words in each name."""
    lv, rv = tokenize_pair(type_pair(left, right, registry.name))
    common = lv.intersection(rv)
    tokens = min(len(lv), len(rv))
    return float(len(common)) / float(max(2.0, tokens))


def name_numbers(left: Entity, right: Entity) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    lv, rv = type_pair(left, right, registry.name)
    return has_disjoint(extract_numbers(lv), extract_numbers(rv))
