import re
import Levenshtein
from itertools import product
from normality import slugify
from functools import lru_cache
from normality.constants import WS
from typing import Callable, Iterable, List
from typing import Optional, Set, Tuple, TypeVar
from followthemoney.types.common import PropertyType

from nomenklatura.entity import CompositeEntity as Entity

V = TypeVar("V")
FIND_NUM = re.compile("\d{2,}")


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


def has_schema(left: Entity, right: Entity, schema: str) -> bool:
    """Check if one of the entities has the required schema."""
    if left.schema.is_a(schema) or right.schema.is_a(schema):
        if not left.schema.can_match(right.schema):
            return False
        return True
    return False


def extract_numbers(values: List[str]) -> Set[str]:
    numbers: Set[str] = set()
    for value in values:
        numbers.update(FIND_NUM.findall(value))
    return numbers


def compare_levenshtein(left: str, right: str) -> float:
    distance = Levenshtein.distance(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))


def props_pair(
    left: Entity, right: Entity, props: List[str]
) -> Tuple[Set[str], Set[str]]:
    left_values: Set[str] = set()
    right_values: Set[str] = set()
    for prop in props:
        left_values.update(left.get(prop, quiet=True))
        right_values.update(right.get(prop, quiet=True))
    return left_values, right_values


def type_pair(
    left: Entity, right: Entity, type_: PropertyType
) -> Tuple[List[str], List[str]]:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return left_values, right_values


def compare_sets(
    left: Iterable[Optional[V]],
    right: Iterable[Optional[V]],
    compare_func: Callable[[V, V], float],
    select_func: Callable[[Iterable[float]], float] = max,
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


@lru_cache(maxsize=1000)
def normalize_text(text: str) -> Optional[str]:
    return slugify(text, sep=WS)


def tokenize(texts: Iterable[str]) -> Set[str]:
    tokens: Set[str] = set()
    for text in texts:
        cleaned = normalize_text(text)
        if cleaned is None:
            continue
        for token in cleaned.split(WS):
            token = token.strip()
            if len(token) > 2:
                tokens.add(token)
    return tokens


def tokenize_pair(
    pair: Tuple[Iterable[str], Iterable[str]]
) -> Tuple[Set[str], Set[str]]:
    return tokenize(pair[0]), tokenize(pair[1])
