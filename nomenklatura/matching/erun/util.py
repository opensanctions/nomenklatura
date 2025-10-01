from normality import ascii_text
from typing import Iterable, Set, Tuple
from rigour.text.distance import levenshtein
from rigour.names import tokenize_name


def tokenize(texts: Iterable[str]) -> Set[str]:
    tokens: Set[str] = set()
    for text in texts:
        text = text.casefold()
        for token in tokenize_name(text):
            ascii_token = ascii_text(token)
            if ascii_token is not None and len(ascii_token) > 2:
                tokens.add(ascii_token)
    return tokens


def tokenize_pair(
    pair: Tuple[Iterable[str], Iterable[str]],
) -> Tuple[Set[str], Set[str]]:
    return tokenize(pair[0]), tokenize(pair[1])


def compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)
