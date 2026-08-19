from collections.abc import Iterable

from normality.constants import WS
from rigour.text.distance import levenshtein

from nomenklatura.matching.compat import clean_name_ascii


def tokenize(texts: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        cleaned = clean_name_ascii(text)
        if cleaned is None:
            continue
        for token in cleaned.split(WS):
            token = token.strip()
            if len(token) > 2:
                tokens.add(token)
    return tokens


def tokenize_pair(
    pair: tuple[Iterable[str], Iterable[str]],
) -> tuple[set[str], set[str]]:
    return tokenize(pair[0]), tokenize(pair[1])


def compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)
