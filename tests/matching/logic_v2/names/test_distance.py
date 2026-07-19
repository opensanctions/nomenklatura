from nomenklatura.matching.logic_v2.names.distance import strict_levenshtein


def test_strict_levenshtein():
    assert strict_levenshtein("abc", "abc") == 1.0
    assert strict_levenshtein("abc", "ab") == 0.0
    assert strict_levenshtein("hello", "hello") == 1.0
    assert strict_levenshtein("hello", "hullo") > 0.0
    assert strict_levenshtein("hello", "hullo") < 1.0
