from typing import List
from followthemoney.proxy import E
from followthemoney.types import registry
from rigour.text.distance import jaro_winkler

from nomenklatura.matching.util import type_pair
from nomenklatura.util import names_word_list, soundex_token


def soundex_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    result_parts = set(names_word_list(result_names_))
    result_soundex = [soundex_token(p) for p in result_parts]
    similiarities: List[float] = []
    for part in set(names_word_list(query_names_)):
        part_soundex = soundex_token(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0
        similiarities.append(soundex_score)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def jaro_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    result_parts = set(names_word_list(result_names_))
    similiarities: List[float] = []
    for part in set(names_word_list(query_names_)):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler(part, other)
            if part_similarity < 0.5:
                part_similarity = 0.0
            best = max(best, part_similarity)

        similiarities.append(best)
    return sum(similiarities) / float(max(1.0, len(similiarities)))
