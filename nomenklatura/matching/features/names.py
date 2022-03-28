import fingerprints
import Levenshtein  # type: ignore
from typing import Iterable, Set, cast
from followthemoney.types import registry
from nomenklatura.entity import CompositeEntity as Entity

from nomenklatura.matching.features.util import has_intersection, has_overlap
from nomenklatura.matching.features.util import compare_sets, tokenize_pair
from nomenklatura.matching.features.util import props_pair, type_pair


def normalize_names(raws: Iterable[str]) -> Set[str]:
    names = set()
    for raw in raws:
        name = fingerprints.generate(raw, keep_order=False)
        if name is not None:
            names.add(name[:128])
    return names


def compare_levenshtein(left: str, right: str) -> float:
    distance = cast(int, Levenshtein.distance(left, right))
    base = max((0, len(left), len(right)))
    return 1 - (distance / base)


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
    return has_intersection(lvn, rvn)


def name_token_overlap(left: Entity, right: Entity) -> float:
    """Evaluate the proportion of identical words in each name."""
    lv, rv = tokenize_pair(type_pair(left, right, registry.name))
    common = lv.intersection(rv)
    tokens = min(len(lv), len(rv))
    return float(len(common)) / float(max(2.0, tokens))
