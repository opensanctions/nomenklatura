from itertools import product
from typing import Callable, Iterable, List, Optional, Sequence, TypeVar


V = TypeVar("V")


def has_intersection(left: Iterable[V], right: Iterable[V]) -> float:
    """Returns 1.0 if there is any overlap between the iterables, else 0.0."""
    if len(set(left).intersection(right)) > 0:
        return 1.0
    return 0.0


def has_disjoint(left: Sequence[V], right: Sequence[V]) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return 1.0
    return 0.0


def compare_sets(
    left: Sequence[Optional[V]],
    right: Sequence[Optional[V]],
    compare_func: Callable[[V, V], float],
    select_func: Callable[[Sequence[float]], float] = max,
) -> float:
    """Compare two sets of values pair-wise and select the highest-scored result."""
    results: List[float] = []
    for (l, r) in product(left, right):
        if l is None or r is None:
            continue
        results.append(compare_func(l, r))
    if not len(results):
        return 0.0
    return select_func(results)
