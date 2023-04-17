import string
import logging
import Levenshtein
from itertools import combinations
from collections import defaultdict
from normality import normalize
from typing import Dict, Optional, List, Tuple

log = logging.getLogger(__name__)
ASCII = set(string.ascii_letters + string.digits + string.whitespace)


def ascii_share(text: str) -> float:
    """Determine the percentage of a string that's in pure ASCII."""
    chars = set(text)
    asciis = ASCII.intersection(chars)
    if len(chars) == 0:
        return 0.0
    return float(len(asciis)) / float(len(chars))


def pick_name(names: List[str]) -> Optional[str]:
    forms: List[Tuple[str, str, float]] = []
    for name in sorted(names):
        norm = normalize(name, ascii=True, lowercase=False)
        if norm is not None:
            weight = 2 - ascii_share(name)
            forms.append((norm, name, weight))
            forms.append((norm.title(), name, weight))

    edits: Dict[str, float] = defaultdict(float)
    cache: Dict[Tuple[str, str], int] = {}
    for ((l_norm, left, l_weight), (r_norm, right, r_weight)) in combinations(forms, 2):
        pair = (l_norm[:128], r_norm[:128])
        if pair not in cache:
            cache[pair] = Levenshtein.distance(*pair)
        edits[left] += cache[pair] * l_weight
        edits[right] += cache[pair] * r_weight

    for cand, _ in sorted(edits.items(), key=lambda x: x[1]):
        return cand
    return None
