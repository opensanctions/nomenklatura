import Levenshtein
from normality.constants import WS
from typing import Iterable, Set

from nomenklatura.util import normalize_name


def has_intersection(left: Iterable[str], right: Iterable[str]) -> float:
    """Returns 1.0 if there is any overlap between the iterables, else 0.0."""
    if len(set(left).intersection(right)) > 0:
        return 1.0
    return 0.0


def has_disjoint(left: Set[str], right: Set[str]) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return 1.0
    return 0.0


def has_overlap(left: Set[str], right: Set[str]) -> float:
    """Returns 1.0 if both sequences overlap, -1.0 if they're non-empty but disjoint."""
    if not len(left) or not len(right):
        return 0.0
    if set(left).isdisjoint(right):
        return -1.0
    return 1.0


def compare_levenshtein(left: str, right: str) -> float:
    distance = Levenshtein.distance(left, right)
    # FIXME: random baseline number
    base = max((15, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)


def tokenize(texts: Iterable[str]) -> Set[str]:
    tokens: Set[str] = set()
    for text in texts:
        cleaned = normalize_name(text)
        if cleaned is None:
            continue
        for token in cleaned.split(WS):
            token = token.strip()
            if len(token) > 2:
                tokens.add(token)
    return tokens