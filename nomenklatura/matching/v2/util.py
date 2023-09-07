from normality.constants import WS
from typing import Iterable, Set

from nomenklatura.util import normalize_name, levenshtein


def compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    # FIXME: random baseline number
    base = max((15, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return ratio if ratio > 0.5 else 0.0
    # return math.sqrt(distance)


def tokenize(texts: Iterable[str]) -> Set[str]:
    tokens: Set[str] = set()
    for text in texts:
        cleaned = normalize_name(text)
        if cleaned is None:
            continue
        for token in cleaned.split(WS):
            token = token.strip()
            if len(token) > 2:
                tokens.add(token)
    return tokens
