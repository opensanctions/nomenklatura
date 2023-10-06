from typing import List, Optional
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from normality.cleaning import decompose_nfkd, category_replace
from fingerprints import clean_name_light, clean_entity_prefix, replace_types
from nomenklatura.util import names_word_list, list_intersection
from nomenklatura.util import phonetic_token, metaphone_token, soundex_token
from nomenklatura.matching.util import type_pair, has_schema


def _clean_phonetic_person(original: str) -> Optional[str]:
    """Normalize a person name without transliteration."""
    text = clean_entity_prefix(original)
    cleaned = clean_name_light(text)
    cleaned = decompose_nfkd(cleaned)
    return category_replace(cleaned)


def _clean_phonetic_entity(original: str) -> Optional[str]:
    """Normalize a legal entity name without transliteration."""
    text = clean_entity_prefix(original)
    cleaned = clean_name_light(text)
    cleaned = decompose_nfkd(cleaned)
    cleaned = category_replace(cleaned)
    return replace_types(cleaned)


def _phonetic_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=_clean_phonetic_person,
        processor=phonetic_token,
        min_length=2,
    )


def _token_names_compare(
    query_names: List[List[str]], result_names: List[List[str]]
) -> float:
    score = 0.0
    for (q, r) in product(query_names, result_names):
        # length = max(2.0, (len(q) + len(r)) / 2.0)
        length = max(2.0, len(q))
        combo = list_intersection(q, r) / float(length)
        score = max(score, combo)
    return score


def person_name_phonetic_match(query: E, result: E) -> float:
    """Two persons have similar names, using a phonetic algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_phonetic_tokens(n) for n in query_names_]
    result_names = [_phonetic_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _metaphone_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=_clean_phonetic_entity,
        processor=metaphone_token,
        min_length=2,
    )


def name_metaphone_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the metaphone
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_metaphone_tokens(n) for n in query_names_]
    result_names = [_metaphone_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _soundex_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=_clean_phonetic_entity,
        processor=soundex_token,
        min_length=2,
    )


def name_soundex_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the soundex
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_tokens(n) for n in query_names_]
    result_names = [_soundex_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)
