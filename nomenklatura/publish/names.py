import string
import logging
from itertools import combinations
from collections import defaultdict
from typing import Dict, Optional, List, Tuple
from nomenklatura.util import normalize_name, levenshtein

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
        norm = normalize_name(name)
        if norm is not None:
            weight = 2 - ascii_share(name)
            forms.append((norm, name, weight))
            forms.append((norm.title(), name, weight))

    edits: Dict[str, float] = defaultdict(float)
    for ((l_norm, left, l_weight), (r_norm, right, r_weight)) in combinations(forms, 2):
        distance = levenshtein(l_norm, r_norm)
        edits[left] += distance * l_weight
        edits[right] += distance * r_weight

    for cand, _ in sorted(edits.items(), key=lambda x: x[1]):
        return cand
    return None
