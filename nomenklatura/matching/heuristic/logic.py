from typing import List, Set, Union
from jellyfish import soundex, jaro_winkler_similarity
from nomenklatura.matching.util import compare_sets
from nomenklatura.util import name_words


def soundex_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    result_parts = name_words(result)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(query):
        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0
        similiarities.append(soundex_score)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def jaro_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two sets of name parts using the Jaro-Winkler string similarity algorithm."""
    result_parts = name_words(result)
    similiarities: List[float] = []
    for part in name_words(query):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            if part_similarity < 0.5:
                part_similarity = 0.0
            best = max(best, part_similarity)

        similiarities.append(best)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def is_disjoint(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False
