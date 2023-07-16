from typing import List, Set, Union
from jellyfish import soundex, jaro_winkler_similarity
from nomenklatura.util import name_words, levenshtein


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
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
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


# def full_name_match(query: List[str], result: List[str]) -> float:
#     """Both entities share the same full name."""
#     overlap = _fingerprint_set(query).intersection(_fingerprint_set(result))
#     return 1.0 if len(overlap) else 0.0


# def _fingerprint_set(names: List[str]) -> Set[str]:
#     fps: Set[str] = set()
#     for name in names:
#         fp = fingerprint_name(name)
#         if fp is not None and len(fp) > 3:
#             fps.add(fp)
#     return fps


def is_disjoint(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False


def compare_identifiers(left: str, right: str) -> float:
    """Overly clever method for comparing tax and company identifiers."""
    if min(len(left), len(right)) < 5:
        return 0.0
    if left in right or right in left:
        return 1.0
    distance = levenshtein(left, right)
    ratio = 1.0 - (distance / float(max(len(left), len(right))))
    return ratio if ratio > 0.7 else 0.0
