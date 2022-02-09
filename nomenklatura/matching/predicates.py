from normality import normalize
from normality.constants import SLUG_CATEGORIES, WS
from functools import lru_cache
from typing import List, Set
from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from nomenklatura.entity import CompositeEntity as Entity


def _entity_key_date(entity: Entity) -> List[str]:
    dates = entity.get("birthDate", quiet=True)
    dates.extend(entity.get("incorporationDate", quiet=True))
    return dates


def _tokenize_set(texts: List[str]) -> Set[str]:
    tokens = set[str]()
    for text in texts:
        cleaned = normalize(text, replace_categories=SLUG_CATEGORIES)
        if cleaned is None:
            continue
        for token in cleaned.split(WS):
            token = token.strip()
            if len(token):
                tokens.add(token)
    # print("TOKENS", tokens)
    return tokens


def _typed_compare(left: Entity, right: Entity, type_: PropertyType) -> float


def key_date_matches(left: Entity, right: Entity) -> float:
    left_dates = _entity_key_date(left)
    right_dates = _entity_key_date(right)
    return registry.date.compare_sets(left_dates, right_dates)


def identifier_matches(left: Entity, right: Entity) -> float:
    left_values = left.get_type_values(registry.identifier)
    right_values = right.get_type_values(registry.identifier)
    return registry.date.compare_sets(left_values, right_values)


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


def name_tokens_weighted(left: Entity, right: Entity) -> float:
    left_tokens = _tokenize_set(left.get_type_values(registry.name))
    right_tokens = _tokenize_set(right.get_type_values(registry.name))
    common = left_tokens.intersection(right_tokens)
    common_len = sum(len(t) for t in common)
    left_tokens_len = sum(len(t) for t in left_tokens)
    right_tokens_len = sum(len(t) for t in right_tokens)
    tokens = max(left_tokens_len, right_tokens_len, 1)
    return float(common_len) / float(tokens)


def common_countries(left: Entity, right: Entity) -> float:
    left_cs = set(left.get_type_values(registry.country))
    right_cs = set(right.get_type_values(registry.country))
    common = left_cs.intersection(right_cs)
    return float(len(common))


def different_countries(left: Entity, right: Entity) -> float:
    left_cs = set(left.get_type_values(registry.country))
    right_cs = set(right.get_type_values(registry.country))
    different = left_cs.symmetric_difference(right_cs)
    return float(len(different))


PREDICATES = [
    name_matches,
    name_tokens,
    name_tokens_weighted,
    common_countries,
    different_countries,
    key_date_matches,
    identifier_matches,
]
