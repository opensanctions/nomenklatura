from typing import List, Optional
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.scripts import is_modern_alphabet
from fingerprints import clean_name_ascii, clean_entity_prefix
from nomenklatura.util import name_words, list_intersection, fingerprint_name
from nomenklatura.util import phonetic_token, metaphone_token, soundex_token
from nomenklatura.matching.util import type_pair, has_schema


def _clean_phonetic_person(original: str) -> Optional[str]:
    """Normalize a person name without transliteration."""
    if not is_modern_alphabet(original):
        return None
    text = clean_entity_prefix(original)
    return clean_name_ascii(text)


def _clean_phonetic_entity(original: str) -> Optional[str]:
    """Normalize a legal entity name without transliteration."""
    if not is_modern_alphabet(original):
        return None
    return fingerprint_name(original)


def _phonetic_person_tokens(token: str) -> List[str]:
    words: List[str] = []
    for word in name_words(_clean_phonetic_person(token), min_length=2):
        words.append(phonetic_token(word))
    return words


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
    query_names = [_phonetic_person_tokens(n) for n in query_names_]
    result_names = [_phonetic_person_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _metaphone_tokens(token: str) -> List[str]:
    words: List[str] = []
    for word in name_words(_clean_phonetic_entity(token), min_length=2):
        words.append(metaphone_token(word))
    return words


def name_metaphone_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the metaphone
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_metaphone_tokens(n) for n in query_names_]
    result_names = [_metaphone_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _soundex_tokens(token: str) -> List[str]:
    words: List[str] = []
    for word in name_words(_clean_phonetic_entity(token), min_length=2):
        words.append(soundex_token(word))
    return words


def name_soundex_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the soundex
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_tokens(n) for n in query_names_]
    result_names = [_soundex_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)
