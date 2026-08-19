from functools import cached_property
from itertools import product

from followthemoney.proxy import E
from followthemoney.types import registry
from normality import ascii_text
from rigour.names import tokenize_name
from rigour.text.distance import is_levenshtein_plausible
from rigour.text.phonetics import metaphone, soundex
from rigour.text.scripts import can_latinize
from rigour.util import list_intersection

from nomenklatura.matching.compat import fingerprint_name, name_words
from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import has_schema, type_pair


class NameTokenPhonetic:
    def __init__(self, token: str):
        self.token = token
        self.ascii = ascii_text(token) if can_latinize(token) else None

    @cached_property
    def metaphone(self) -> str | None:
        if self.ascii is not None:
            phoneme = metaphone(self.ascii)
            if len(phoneme) >= 3:
                return phoneme
        return None

    # def __repr__(self) -> str:
    #     return f"<NameTokenPhonetic {self.token!r}, {self.ascii!r}, {self.metaphone!r}>"

    @classmethod
    def from_name(cls, name: str) -> list["NameTokenPhonetic"]:
        tokens = tokenize_name(name.casefold(), token_min_length=2)
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
    if left.metaphone is not None and right.metaphone is not None:
        if left.metaphone == right.metaphone:
            # Secondary check for Levenshtein distance:
            if left.ascii is not None and right.ascii is not None:
                if is_levenshtein_plausible(left.ascii, right.ascii):
                    return True
    return left.token == right.token


def _clean_phonetic_entity(original: str) -> str | None:
    """Normalize a legal entity name without transliteration."""
    if not can_latinize(original):
        return None
    return fingerprint_name(original)


def _token_names_compare(
    query_names: list[list[str]], result_names: list[list[str]]
) -> float:
    score = 0.0
    for q, r in product(query_names, result_names):
        # length = max(2.0, (len(q) + len(r)) / 2.0)
        length = max(2.0, len(q))
        combo = len(list_intersection(q, r)) / float(length)
        score = max(score, combo)
    return score


def person_name_phonetic_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two persons have similar names, using a phonetic algorithm."""
    if not has_schema(query, result, "Person"):
        return FtResult(score=0.0, detail=None)
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
    return FtResult(score=score, detail=None)


def _metaphone_tokens(token: str) -> list[str]:
    words: list[str] = []
    for word in name_words(_clean_phonetic_entity(token), min_length=2):
        words.append(metaphone_token(word))
    return words


def name_metaphone_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities (person and non-person) have similar names, using the metaphone
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_metaphone_tokens(n) for n in query_names_]
    result_names = [_metaphone_tokens(n) for n in result_names_]
    return FtResult(score=_token_names_compare(query_names, result_names), detail=None)


def _soundex_tokens(token: str) -> list[str]:
    words: list[str] = []
    for word in name_words(_clean_phonetic_entity(token), min_length=2):
        words.append(soundex_token(word))
    return words


def name_soundex_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities (person and non-person) have similar names, using the soundex
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_tokens(n) for n in query_names_]
    result_names = [_soundex_tokens(n) for n in result_names_]
    return FtResult(score=_token_names_compare(query_names, result_names), detail=None)
