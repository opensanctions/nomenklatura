from functools import cached_property
from typing import List, Optional
from itertools import product
from normality import ascii_text
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.scripts import can_latinize
from rigour.text.distance import is_levenshtein_plausible
from rigour.text.phonetics import metaphone, soundex
from rigour.names import tokenize_name
from rigour.util import list_intersection

from nomenklatura.matching.util import type_pair, has_schema
from nomenklatura.matching.compat import fingerprint_name, name_words


class NameTokenPhonetic:
    def __init__(self, token: str):
        self.token = token
        self.ascii = ascii_text(token) if can_latinize(token) else None

    @cached_property
    def metaphone(self) -> Optional[str]:
        if self.ascii is not None:
            phoneme = metaphone(self.ascii)
            if len(phoneme) >= 3:
                return phoneme
        return None

    # def __repr__(self) -> str:
    #     return f"<NameTokenPhonetic {self.token!r}, {self.ascii!r}, {self.metaphone!r}>"

    @classmethod
    def from_name(cls, name: str) -> List["NameTokenPhonetic"]:
        tokens = tokenize_name(name.lower(), token_min_length=2)
        return [cls(token) for token in tokens]


def metaphone_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        out = metaphone(token)
        # doesn't handle non-ascii characters
        if len(out) >= 3:
            return out
    return token.upper()


def soundex_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        out = soundex(token)
        # doesn't handle non-ascii characters
        if len(out):
            return out
    return token.upper()


def compare_parts_phonetic(left: NameTokenPhonetic, right: NameTokenPhonetic) -> bool:
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


def _clean_phonetic_entity(original: str) -> Optional[str]:
    """Normalize a legal entity name without transliteration."""
    if not can_latinize(original):
        return None
    return fingerprint_name(original)


def _token_names_compare(
    query_names: List[List[str]], result_names: List[List[str]]
) -> float:
    score = 0.0
    for q, r in product(query_names, result_names):
        # length = max(2.0, (len(q) + len(r)) / 2.0)
        length = max(2.0, len(q))
        combo = len(list_intersection(q, r)) / float(length)
        score = max(score, combo)
    return score


def person_name_phonetic_match(query: E, result: E) -> float:
    """Two persons have similar names, using a phonetic algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_parts = [NameTokenPhonetic.from_name(n) for n in query_names_]
    result_parts = [NameTokenPhonetic.from_name(n) for n in result_names_]
    score = 0.0
    for q, r in product(query_parts, result_parts):
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
