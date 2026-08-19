import re
from collections.abc import Callable, Iterable
from typing import Optional

CleanFunc = Optional[Callable[[str], str | None]]
FIND_NUM = re.compile(r"\d{1,}")


def is_disjoint(
    left: set[str] | list[str],
    right: set[str] | list[str],
) -> bool:
    """Returns true if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False


def has_overlap(
    left: set[str] | list[str],
    right: set[str] | list[str],
) -> bool:
    """Returns true if both sequences are non-empty and have common values."""
    if not set(left).isdisjoint(right):
        return True
    return False


def clean_map(
    texts: Iterable[str | None],
    clean: CleanFunc = None,
) -> set[str]:
    """Apply a cleaning function to a set of strings and only return non-empty ones."""
    out: set[str] = set()
    for text in texts:
        if text is None or len(text) == 0:
            continue
        if clean is not None:
            text = clean(text)
            if text is None or len(text) == 0:
                continue
        out.add(text)
    return out


def extract_numbers(values: list[str]) -> set[str]:
    """Extract all numbers from a list of strings."""
    numbers: set[str] = set()
    for value in values:
        numbers.update(FIND_NUM.findall(value))
    return numbers
