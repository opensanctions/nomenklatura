import re
from typing import List, Set, Union, Iterable, Callable, Optional

CleanFunc = Optional[Callable[[str], Optional[str]]]
FIND_NUM = re.compile(r"\d{1,}")


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


def extract_numbers(values: List[str]) -> Set[str]:
    """Extract all numbers from a list of strings."""
    numbers: Set[str] = set()
    for value in values:
        numbers.update(FIND_NUM.findall(value))
    return numbers
