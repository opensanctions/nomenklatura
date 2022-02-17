import fingerprints
from typing import List, Optional, Set
from functools import lru_cache
from normality import normalize
from normality.constants import SLUG_CATEGORIES, WS
from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from nomenklatura.entity import CompositeEntity as Entity


def _entity_key_date(entity: Entity) -> List[str]:
    dates = entity.get("birthDate", quiet=True)
    dates.extend(entity.get("incorporationDate", quiet=True))
    return dates


@lru_cache(maxsize=5000)
def fp_gen(text: str) -> Optional[str]:
    return fingerprints.generate(text)


@lru_cache(maxsize=5000)
def _clean_text(text: str) -> List[str]:
    tokens: List[str] = []
    cleaned = normalize(text, latinize=True, replace_categories=SLUG_CATEGORIES)
    if cleaned is None:
        return tokens
    for token in cleaned.split(WS):
        token = token.strip()
        if len(token):
            tokens.append(token)
    return tokens


def _tokenize_set(texts: List[str]) -> Set[str]:
    tokens = set[str]()
    for text in texts:
        tokens.update(_clean_text(text))
        # cleaned = normalize(text, replace_categories=SLUG_CATEGORIES)
        # if cleaned is None:
        #     continue
        # for token in cleaned.split(WS):
        #     token = token.strip()
        #     if len(token):
        #         tokens.add(token)
    # print("TOKENS", tokens)
    return tokens


def _typed_compare(left: Entity, right: Entity, type_: PropertyType) -> float:
    left_values = left.get_type_values(type_)
    right_values = right.get_type_values(type_)
    return registry.date.compare_sets(left_values, right_values)


def key_date_matches(left: Entity, right: Entity) -> float:
    left_dates = _entity_key_date(left)
    right_dates = _entity_key_date(right)
    return registry.date.compare_sets(left_dates, right_dates)


def phone_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.phone)


def email_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.email)


def name_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.name)


def identifier_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.identifier)


def country_ftm_compare(left: Entity, right: Entity) -> float:
    return _typed_compare(left, right, registry.country)


def name_matches(left: Entity, right: Entity) -> float:
    left_names = set([n.lower() for n in left.get_type_values(registry.name)])
    right_names = set([n.lower() for n in right.get_type_values(registry.name)])
    common = left_names.intersection(right_names)
    return float(len(common))


def name_tokens(left: Entity, right: Entity) -> float:
    left_tokens = _tokenize_set(left.get_type_values(registry.name))
    right_tokens = _tokenize_set(right.get_type_values(registry.name))
    common = left_tokens.intersection(right_tokens)
    tokens = max(len(left_tokens), len(right_tokens), 1)
    return float(len(common)) / float(tokens)


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


def name_fingerprints_weighted(left: Entity, right: Entity) -> float:
    left_values = [fp_gen(n) for n in left.get_type_values(registry.name)]
    left_values_ = [n for n in left_values if n is not None]
    right_values = [fp_gen(n) for n in right.get_type_values(registry.name)]
    right_values_ = [n for n in right_values if n is not None]
    return _tokens_weighted(left_values_, right_values_)


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


def common_countries(left: Entity, right: Entity) -> float:
    left_cs = set(left.get_type_values(registry.country))
    right_cs = set(right.get_type_values(registry.country))
    # num = max(1, max(len(left_cs), len(right_cs)))
    common = left_cs.intersection(right_cs)
    return min(1.0, float(len(common)) / float(3))


def different_countries(left: Entity, right: Entity) -> float:
    left_cs = set(left.get_type_values(registry.country))
    right_cs = set(right.get_type_values(registry.country))
    different = left_cs.symmetric_difference(right_cs)
    return float(len(different))


def schema_compare(left: Entity, right: Entity) -> float:
    if left.schema == right.schema:
        return 1.0
    if left.schema in right.schema.matchable_schemata:
        return 0.9
    return 0.0


FEATURES = [
    name_matches,
    name_tokens,
    name_tokens_weighted,
    name_fingerprints_weighted,
    address_tokens_weighted,
    all_tokens_weighted,
    common_countries,
    different_countries,
    key_date_matches,
    phone_ftm_compare,
    name_ftm_compare,
    email_ftm_compare,
    identifier_ftm_compare,
    country_ftm_compare,
    schema_compare,
]
