from typing import List, Optional, Tuple
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.distance import jaro_winkler
from rigour.text.phonetics import soundex

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import type_pair
from nomenklatura.matching.compat import names_word_list


def _soundex_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        out = soundex(token)
        # doesn't handle non-ascii characters
        if len(out):
            return out
    return token.upper()


def soundex_name_parts(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Compare two sets of name parts using the phonetic matching."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_soundex = set([_soundex_token(p) for p in names_word_list(query_names_)])
    result_soundex = set([_soundex_token(p) for p in names_word_list(result_names_)])
    overlap = query_soundex.intersection(result_soundex)
    if len(overlap) == 0:
        return FtResult(score=0.0, detail=None)
    min_len = min(len(query_soundex), len(result_soundex))
    score = len(overlap) / float(max(1.0, min_len))
    detail = f"Matched {len(overlap)} tokens: {', '.join(overlap)}"
    return FtResult(score=score, detail=detail)


def jaro_name_parts(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    result_parts = set(names_word_list(result_names_))
    similiarities: List[float] = []
    tokens: List[Tuple[str, str]] = []
    for part in set(names_word_list(query_names_)):
        best = 0.0
        best_token: Optional[str] = None

        for other in result_parts:
            part_similarity = jaro_winkler(part, other)
            if part_similarity > 0.5 and part_similarity > best:
                best = part_similarity
                best_token = other

        similiarities.append(best)
        if best_token is not None:
            tokens.append((part, best_token))
    if len(similiarities) == 0:
        return FtResult(score=0.0, detail=None)
    score = sum(similiarities) / float(max(1.0, len(similiarities)))
    mapping = ", ".join(f"{a} -> {b}" for a, b in tokens)
    return FtResult(score=score, detail=f"Matched {len(tokens)} tokens: {mapping}")
