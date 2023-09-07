from typing import List, Set, Union


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
