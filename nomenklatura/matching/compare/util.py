from typing import List, Set, Union, Iterable, Callable, Optional

from nomenklatura.util import levenshtein

CleanFunc = Optional[Callable[[str], Optional[str]]]


def is_disjoint(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> bool:
    """Returns true if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False


def has_overlap(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> bool:
    """Returns true if both sequences are non-empty and have common values."""
    if len(set(left).intersection(right)) > 0:
        return True
    return False


def clean_map(
    texts: Iterable[Optional[str]],
    clean: CleanFunc = None,
) -> Set[str]:
    """Apply a cleaning function to a set of strings and only return non-empty ones."""
    out: Set[str] = set()
    for text in texts:
        if text is None or len(text) == 0:
            continue
        if clean is not None:
            text = clean(text)
            if text is None or len(text) == 0:
                continue
        out.add(text)
    return out


def compare_levenshtein(left: str, right: str) -> float:
    """Generate a similarity score out of a levenshtein distance for two names."""
    shortest = float(min(len(left), len(right)))
    if shortest == 0.0:
        return 0.0
    distance = levenshtein(left, right)
    max_error = min(15.0, shortest * 0.7)
    if distance > max_error:
        return 0.0
    return 1.0 - (distance / shortest)
