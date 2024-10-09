from normality.constants import WS
from typing import Iterable, Set, Tuple
from rigour.text.distance import levenshtein

from nomenklatura.util import normalize_name


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


def tokenize_pair(
    pair: Tuple[Iterable[str], Iterable[str]]
) -> Tuple[Set[str], Set[str]]:
    return tokenize(pair[0]), tokenize(pair[1])


def compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)
