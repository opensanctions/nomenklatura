from attr import has
import fingerprints
import Levenshtein
from typing import Callable, Iterable, List, Optional, Sequence, Set, TypeVar
from itertools import product
from functools import lru_cache
from normality import normalize
from prefixdate import Precision
from normality.constants import SLUG_CATEGORIES, WS
from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.index.util import split_ngrams

V = TypeVar("V")


def has_intersection(left: Iterable[V], right: Iterable[V]) -> float:
    if len(set(left).intersection(right)) > 0:
        return 1.0
    return 0.0


def has_disjoint(left: Sequence[V], right: Sequence[V]) -> float:
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
    """Compare two sets of values and select the highest-scored result."""
    results = []
    for (l, r) in product(left, right):
        if l is None or r is None:
            continue
        results.append(compare_func(l, r))
    if not len(results):
        return 0.0
    return select_func(results)


def normalize_name(text: Optional[str], keep_order=True) -> Optional[str]:
    # name = fingerprints.generate(text, keep_order=keep_order)
    name = normalize(text, latinize=True)
    if name is not None:
        return name[:128]
    return name


def compare_names_jaro(left: str, right: str) -> float:
    return Levenshtein.jaro_winkler(left, right)


# def compare_names_edit(left: str, right: str) -> float:
#     distance = Levenshtein.distance(left, right)


def name_normalized(left: Entity, right: Entity) -> float:
    left_values = [normalize_name(n) for n in left.get_type_values(registry.name)]
    right_values = [normalize_name(n) for n in right.get_type_values(registry.name)]
    return compare_sets(left_values, right_values, compare_names_jaro)


@lru_cache(maxsize=5000)
def _clean_text(text: str) -> List[str]:
    tokens: List[str] = []
    cleaned = normalize(text, latinize=True, replace_categories=SLUG_CATEGORIES)
    if cleaned is None:
        return tokens
    for token in cleaned.split(WS):
        token = token.strip()
        if len(token) > 2:
            tokens.append(token)
    return tokens


def _tokenize_set(texts: List[str]) -> Set[str]:
    tokens = set[str]()
    for text in texts:
        tokens.update(_clean_text(text))
    return tokens


def _entity_key_dates(entity: Entity) -> List[str]:
    values = entity.get("birthDate", quiet=True)
    values.extend(entity.get("incorporationDate", quiet=True))
    return values


def _dates_precision(values: Iterable[str], precision: Precision):
    dates = set()
    for value in values:
        if len(value) >= precision.value:
            dates.add(value[: precision.value])
    return dates


def key_day_matches(left: Entity, right: Entity) -> float:
    left_days = _dates_precision(_entity_key_dates(left), Precision.DAY)
    right_days = _dates_precision(_entity_key_dates(right), Precision.DAY)
    return has_intersection(left_days, right_days)


def key_day_disjoint(left: Entity, right: Entity) -> float:
    left_days = _dates_precision(_entity_key_dates(left), Precision.DAY)
    right_days = _dates_precision(_entity_key_dates(right), Precision.DAY)
    return has_disjoint(left_days, right_days)


def key_year_matches(left: Entity, right: Entity) -> float:
    left_dates = _entity_key_dates(left)
    right_dates = _entity_key_dates(right)
    left_years = _dates_precision(left_dates, Precision.YEAR)
    right_years = _dates_precision(right_dates, Precision.YEAR)
    if len(left_years.intersection(right_dates)) > 0:
        return 1.0
    if len(right_years.intersection(left_dates)) > 0:
        return 1.0
    return 0.0


def _typed_compare(left: Entity, right: Entity, type_: PropertyType) -> float:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return type_.compare_sets(left_values, right_values)


def _typed_intersection(left: Entity, right: Entity, type_: PropertyType) -> float:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return has_intersection(left_values, right_values)


# def phone_ftm_compare(left: Entity, right: Entity) -> float:
#     return _typed_compare(left, right, registry.phone)


def phone_intersection(left: Entity, right: Entity) -> float:
    return _typed_intersection(left, right, registry.phone)


def email_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.email)


def email_intersection(left: Entity, right: Entity) -> float:
    return _typed_intersection(left, right, registry.email)


def name_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.name)


def identifier_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.identifier)


def identifier_intersection(left: Entity, right: Entity) -> float:
    return _typed_intersection(left, right, registry.identifier)


# def country_ftm_compare(left: Entity, right: Entity) -> float:
#     return _typed_compare(left, right, registry.country)


def country_intersection(left: Entity, right: Entity) -> float:
    return _typed_intersection(left, right, registry.country)


def country_disjoint(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.country)
    right_values = right.get_type_values(registry.country)
    return has_disjoint(left_values, right_values)


def name_matches(left: Entity, right: Entity) -> float:
    left_names = set([n.lower() for n in left.get_type_values(registry.name)])
    right_names = set([n.lower() for n in right.get_type_values(registry.name)])
    return has_intersection(left_names, right_names)


def name_tokens(left: Entity, right: Entity) -> float:
    left_tokens = _tokenize_set(left.get_type_values(registry.name))
    right_tokens = _tokenize_set(right.get_type_values(registry.name))
    common = left_tokens.intersection(right_tokens)
    tokens = min(len(left_tokens), len(right_tokens))
    return float(len(common)) / float(max(2.0, tokens))


def _ngram_prep_names(names: List[str]) -> List[Set[str]]:
    ngrams = []
    for name in names:
        ngrams.append(set(split_ngrams(name, 2, 4)))
    return ngrams


def _ngram_compare(left: Set[str], right: Set[str]) -> float:
    common = left.intersection(right)
    tokens = min(len(left), len(right))
    return float(len(common)) / float(max(2.0, tokens))


def name_ngrams_exp(left: Entity, right: Entity) -> float:
    left_grams = _ngram_prep_names(left.get_type_values(registry.name))
    right_ngrams = _ngram_prep_names(right.get_type_values(registry.name))
    return compare_sets(left_grams, right_ngrams, _ngram_compare)


def _tokens_weighted(left: List[str], right: List[str]) -> float:
    left_tokens = _tokenize_set(left)
    right_tokens = _tokenize_set(right)
    common = left_tokens.intersection(right_tokens)
    common_len = sum(len(t) for t in common)
    left_tokens_len = sum(len(t) for t in left_tokens)
    right_tokens_len = sum(len(t) for t in right_tokens)
    tokens = max(left_tokens_len, right_tokens_len, 1)
    return float(common_len) / float(tokens)


def name_tokens_weighted(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.name)
    right_values = right.get_type_values(registry.name)
    return _tokens_weighted(left_values, right_values)


# def name_fingerprints_weighted(left: Entity, right: Entity) -> float:
#     left_values = [fp_gen(n) for n in left.get_type_values(registry.name)]
#     left_values_ = [n for n in left_values if n is not None]
#     right_values = [fp_gen(n) for n in right.get_type_values(registry.name)]
#     right_values_ = [n for n in right_values if n is not None]
#     return _tokens_weighted(left_values_, right_values_)


def address_tokens_weighted(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.address)
    if left.schema.is_a("Address"):
        left_values.extend(left.get("full"))
    right_values = right.get_type_values(registry.address)
    if right.schema.is_a("Address"):
        right_values.extend(right.get("full"))
    return _tokens_weighted(left_values, right_values)


def all_tokens_weighted(left: Entity, right: Entity) -> float:
    left_values = [v for _, v in left.itervalues()]
    right_values = [v for _, v in right.itervalues()]
    return _tokens_weighted(left_values, right_values)


# def common_countries(left: Entity, right: Entity) -> float:
#     left_cs = set(left.get_type_values(registry.country))
#     right_cs = set(right.get_type_values(registry.country))
#     # num = max(1, max(len(left_cs), len(right_cs)))
#     common = left_cs.intersection(right_cs)
#     return min(1.0, float(len(common)) / float(3))


# def different_countries(left: Entity, right: Entity) -> float:
#     left_cs = set(left.get_type_values(registry.country))
#     right_cs = set(right.get_type_values(registry.country))
#     different = left_cs.symmetric_difference(right_cs)
#     return float(len(different))


def schema_same(left: Entity, right: Entity) -> float:
    if left.schema == right.schema:
        return 1.0
    return 0.0


def schema_matchable(left: Entity, right: Entity) -> float:
    if left.schema in right.schema.matchable_schemata:
        return 1.0
    return 0.0


FEATURES = [
    name_matches,
    name_tokens,
    # name_ngrams_exp,
    name_normalized,
    # name_tokens_weighted,
    # address_tokens_weighted,
    # all_tokens_weighted,
    # phone_ftm_compare,
    email_ftm_compare,
    identifier_ftm_compare,
    # country_ftm_compare,
    # name_normalized,
    key_day_matches,
    key_day_disjoint,
    key_year_matches,
    # name_ftm_compare,
    phone_intersection,
    email_intersection,
    # identifier_intersection,
    country_intersection,
    country_disjoint,
    # schema_same,
    schema_matchable,
]
