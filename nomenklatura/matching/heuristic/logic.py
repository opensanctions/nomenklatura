from typing import List
from followthemoney.proxy import E
from followthemoney.types import registry
from jellyfish import soundex, jaro_winkler_similarity
from nomenklatura.util import name_words
from nomenklatura.matching.util import type_pair


def soundex_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    query_names, result_names = type_pair(query, result, registry.name)
    result_parts = name_words(query_names)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(result_names):
        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0
        similiarities.append(soundex_score)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def jaro_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
    query_names, result_names = type_pair(query, result, registry.name)
    result_parts = name_words(query_names)
    similiarities: List[float] = []
    for part in name_words(result_names):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            if part_similarity < 0.5:
                part_similarity = 0.0
            best = max(best, part_similarity)

        similiarities.append(best)
    return sum(similiarities) / float(max(1.0, len(similiarities)))
