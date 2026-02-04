from rigour.text.distance import levenshtein


def compare_levenshtein(left: str, right: str) -> float:
    distance = levenshtein(left, right)
    base = max((1, len(left), len(right)))
    return 1.0 - (distance / float(base))
    # return math.sqrt(distance)
