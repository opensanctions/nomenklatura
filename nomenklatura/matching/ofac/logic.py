from typing import List, Set, Union
from jellyfish import soundex, jaro_winkler_similarity
from nomenklatura.matching.util import compare_sets
from nomenklatura.util import name_words


def soundex_jaro_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two strings using the Soundex algorithm and Jaro-Winkler."""
    result_parts = name_words(result)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(query):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            best = max(best, part_similarity)

        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0

        # OFAC is very unspecific on this part, so this is a best guess:
        part_score = (best + soundex_score) / 2

        similiarities.append(part_score)
    return sum(similiarities) / float(len(similiarities))


def name_jaro_winkler(query: List[str], result: List[str]) -> float:
    return compare_sets(query, result, jaro_winkler_similarity)


def ofac_round_score(score: float, precision: float = 0.05) -> float:
    """OFAC seems to return scores in steps of 5, ie. 100, 95, 90, 85, etc."""
    correction = 0.5 if score >= 0 else -0.5
    return round(int(score / precision + correction) * precision, 2)


def is_disjoint(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False
