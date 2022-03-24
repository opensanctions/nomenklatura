import fingerprints
import Levenshtein  # type: ignore
from typing import Callable, Iterable, List, Optional, Sequence, Set, TypeVar
from functools import lru_cache, cache
from normality import normalize
from normality.constants import SLUG_CATEGORIES, WS
from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from nomenklatura.entity import CompositeEntity as Entity

from nomenklatura.matching.util import has_disjoint, has_intersection
from nomenklatura.matching.util import compare_sets
from nomenklatura.matching.dates import key_day_disjoint, key_day_matches
from nomenklatura.matching.dates import key_year_matches


@cache
def normalize_name(text: Optional[str], keep_order=False) -> Optional[str]:
    name = fingerprints.generate(text, keep_order=keep_order)
    if name is not None:
        return name[:128]
    return name


def compare_names_jaro(left: str, right: str) -> float:
    return Levenshtein.jaro_winkler(left, right)  # type: ignore


# def name_jaro_winkler(left: Entity, right: Entity) -> float:
#     left_values = [
#         normalize_name(n, keep_order=True) for n in left.get_type_values(registry.name)
#     ]
#     right_values = [
#         normalize_name(n, keep_order=True) for n in right.get_type_values(registry.name)
#     ]
#     return compare_sets(left_values, right_values, compare_names_jaro)


def compare_levenshtein(left: str, right: str) -> float:
    distance = Levenshtein.distance(left, right)
    # if distance == 0:
    #     return 0.0
    base = max((0, len(left), len(right)))
    return 1 - (distance / base)


def name_levenshtein(left: Entity, right: Entity) -> float:
    left_values = [normalize_name(n) for n in left.get_type_values(registry.name)]
    right_values = [normalize_name(n) for n in right.get_type_values(registry.name)]
    return compare_sets(left_values, right_values, compare_levenshtein)


@lru_cache(maxsize=5000)
def _clean_text(text: str) -> List[str]:
    tokens: List[str] = []
    cleaned = normalize(text, ascii=True)
    if cleaned is None:
        return tokens
    for token in cleaned.split(WS):
        token = token.strip()
        if len(token) > 2:
            tokens.append(token)
    return tokens


def _tokenize_set(texts: Iterable[str]) -> Set[str]:
    tokens = set[str]()
    for text in texts:
        tokens.update(_clean_text(text))
    return tokens


def _typed_compare(left: Entity, right: Entity, type_: PropertyType) -> float:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return type_.compare_sets(left_values, right_values)


def _typed_intersection(left: Entity, right: Entity, type_: PropertyType) -> float:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return has_intersection(left_values, right_values)


def _props_pair(left: Entity, right: Entity, props: List[str]):
    left_values: Set[str] = set()
    right_values: Set[str] = set()
    for prop in props:
        left_values.update(left.get(prop, quiet=True))
        right_values.update(right.get(prop, quiet=True))
    return left_values, right_values


def _props_match(
    left: Entity, right: Entity, props: List[str], max: float = 3.0
) -> float:
    lv, rv = _props_pair(left, right, props)
    lv = _tokenize_set(lv)
    rv = _tokenize_set(rv)
    # overlap = len(left_values.intersection(right_values))
    # print("NAMES", left_values, right_values)
    # return min(max, len(set(lv).intersection(rv))) / float(max)
    # return compare_sets(lv, rv, compare_names_jaro)
    return has_disjoint(lv, rv)
    # return has_intersection(lv, rv)


def birth_place(left: Entity, right: Entity) -> float:
    lv, rv = _props_pair(left, right, ["birthPlace"])
    lv = _tokenize_set(lv)
    rv = _tokenize_set(rv)
    overlap = len(lv.intersection(rv))
    base = max(1, min(len(lv), len(rv)))
    return 1 - (overlap / base)


def first_name_match(left: Entity, right: Entity) -> float:
    """Person first name matches."""
    props = ["firstName"]
    return _props_match(left, right, props)
    # return 0.0


def middle_names(left: Entity, right: Entity) -> float:
    props = ["secondName", "middleName", "fatherName"]
    # props = ["secondName", "middleName"]
    return _props_match(left, right, props)
    # return 0.0


def family_names(left: Entity, right: Entity) -> float:
    props = ["lastName"]
    return _props_match(left, right, props)


def gender_disjoint(left: Entity, right: Entity) -> float:
    lv = [v for v in left.get("gender", quiet=True) if v in ("male", "female")]
    rv = [v for v in right.get("gender", quiet=True) if v in ("male", "female")]
    return has_disjoint(lv, rv)
    # print("GENDER", lv, rv)
    # return 1.0
    # return has_disjoint(
    #     left.get("gender", quiet=True),
    #     right.get("gender", quiet=True),
    # )


def phone_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.phone)


def phone_mismatch(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.phone)
    right_values = right.get_type_values(registry.phone)
    return has_disjoint(left_values, right_values)


# def phone_intersection(left: Entity, right: Entity) -> float:
#     return _typed_intersection(left, right, registry.phone)


def email_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.email)


# def email_intersection(left: Entity, right: Entity) -> float:
#     return _typed_intersection(left, right, registry.email)


def name_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.name)


def identifier_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.identifier)


# def identifier_intersection(left: Entity, right: Entity) -> float:
#     return _typed_intersection(left, right, registry.identifier)


# def country_ftm_compare(left: Entity, right: Entity) -> float:
#     return _typed_compare(left, right, registry.country)


def country_intersection(left: Entity, right: Entity) -> float:
    return _typed_intersection(left, right, registry.country)


def country_disjoint(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.country)
    right_values = right.get_type_values(registry.country)
    return has_disjoint(left_values, right_values)


def name_matches(left: Entity, right: Entity) -> float:
    left_names = set([normalize_name(n) for n in left.get_type_values(registry.name)])
    right_names = set([normalize_name(n) for n in right.get_type_values(registry.name)])
    return has_intersection(left_names, right_names)


def name_tokens(left: Entity, right: Entity) -> float:
    left_tokens = _tokenize_set(left.get_type_values(registry.name))
    right_tokens = _tokenize_set(right.get_type_values(registry.name))
    common = left_tokens.intersection(right_tokens)
    tokens = min(len(left_tokens), len(right_tokens))
    return float(len(common)) / float(max(2.0, tokens))


# def _ngram_prep_names(names: List[str]) -> List[Set[str]]:
#     ngrams = []
#     for name in names:
#         ngrams.append(set(split_ngrams(name, 2, 4)))
#     return ngrams


# def _ngram_compare(left: Set[str], right: Set[str]) -> float:
#     common = left.intersection(right)
#     tokens = min(len(left), len(right))
#     return float(len(common)) / float(max(2.0, tokens))


# def name_ngrams_exp(left: Entity, right: Entity) -> float:
#     left_grams = _ngram_prep_names(left.get_type_values(registry.name))
#     right_ngrams = _ngram_prep_names(right.get_type_values(registry.name))
#     return compare_sets(left_grams, right_ngrams, _ngram_compare)


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


# def address_tokens_weighted(left: Entity, right: Entity) -> float:
#     left_values = left.get_type_values(registry.address)
#     if left.schema.is_a("Address"):
#         left_values.extend(left.get("full"))
#     right_values = right.get_type_values(registry.address)
#     if right.schema.is_a("Address"):
#         right_values.extend(right.get("full"))
#     return _tokens_weighted(left_values, right_values)


# def all_tokens_weighted(left: Entity, right: Entity) -> float:
#     left_values = [v for _, v in left.itervalues()]
#     right_values = [v for _, v in right.itervalues()]
#     return _tokens_weighted(left_values, right_values)


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


def schema_match(left: Entity, right: Entity) -> float:
    """The type of both entities matches exactly."""
    if left.schema == right.schema:
        return 1.0
    return 0.0


FEATURES = [
    name_matches,
    name_tokens,
    # name_ngrams_exp,
    # name_jaro_winkler,
    name_levenshtein,
    # name_tokens_weighted,
    # address_tokens_weighted,
    # all_tokens_weighted,
    phone_ftm_compare,
    email_ftm_compare,
    identifier_ftm_compare,
    # country_ftm_compare,
    # name_normalized,
    key_day_matches,
    key_day_disjoint,
    key_year_matches,
    birth_place,
    first_name_match,
    middle_names,
    family_names,
    gender_disjoint,
    phone_mismatch,
    # name_ftm_compare,
    # phone_intersection,
    # email_intersection,
    # identifier_intersection,
    # country_intersection,
    country_disjoint,
    schema_match,
    # schema_matchable,
]
