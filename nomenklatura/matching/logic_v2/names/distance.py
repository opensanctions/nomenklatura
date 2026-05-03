from functools import lru_cache

from rigour.text import levenshtein

from nomenklatura.matching.util import MEMO_BATCH


@lru_cache(maxsize=MEMO_BATCH)
def strict_levenshtein(left: str, right: str, max_rate: int = 4) -> float:
    """Calculate the string distance between two strings."""
    if left == right:
        return 1.0
    max_len = max(len(left), len(right))
    max_edits = max_len // max_rate
    if max_edits < 1:  # We already checked for equality
        return 0.0
    distance = levenshtein(left, right, max_edits=max_len)
    if distance > max_edits:
        return 0.0
    return (1 - (distance / max_len)) ** max_edits
