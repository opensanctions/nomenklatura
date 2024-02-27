from typing import List, Optional
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.scripts import is_modern_alphabet
from rigour.text.distance import is_levenshtein_plausible
from rigour.names.part import name_parts, NamePart
from nomenklatura.util import name_words, list_intersection, fingerprint_name
from nomenklatura.util import metaphone_token, soundex_token
from nomenklatura.matching.util import type_pair, has_schema


def compare_parts_phonetic(left: NamePart, right: NamePart) -> bool:
    if left.metaphone is None or right.metaphone is None:
        return left.ascii == right.ascii
    if (
        left.metaphone == right.metaphone
        and left.ascii is not None
        and right.ascii is not None
    ):
        # Secondary check for Levenshtein distance:
        if is_levenshtein_plausible(left.ascii, right.ascii):
            return True
    return False


# def _clean_phonetic_person(original: str) -> Optional[str]:
#     """Normalize a person name without transliteration."""
#     if not is_modern_alphabet(original):
#         return None
#     text = clean_entity_prefix(original)
#     return clean_name_ascii(text)


def _clean_phonetic_entity(original: str) -> Optional[str]:
    """Normalize a legal entity name without transliteration."""
    if not is_modern_alphabet(original):
        return None
    return fingerprint_name(original)


# def _phonetic_person_tokens(token: str) -> List[str]:
#     words: List[str] = []
#     for word in name_words(_clean_phonetic_person(token), min_length=2):
#         words.append(phonetic_token(word))
#     return words


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
    query_parts = [name_parts(n) for n in query_names_]
    result_parts = [name_parts(n) for n in result_names_]
    score = 0.0
    for (q, r) in product(query_parts, result_parts):
        if len(q) == 0:
            continue
        matches = list(r)
        matched = 0
        for part in q:
            for other in matches:
                if compare_parts_phonetic(part, other):
                    matches.remove(other)
                    matched += 1
                    break
        score = max(score, matched / float(len(q)))
    return score


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
