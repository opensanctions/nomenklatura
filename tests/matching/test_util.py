from nomenklatura.matching.compare.util import compare_levenshtein


def test_compare_levenshtein():
    assert compare_levenshtein("John Smith", "John Smith") == 1.0
    johnny = compare_levenshtein("John Smith", "Johnny Smith")
    assert johnny < 1.0
    assert johnny > 0.5
    johnathan = compare_levenshtein("John Smith", "Johnathan Smith")
    assert johnathan < 1.0
    assert johnathan > 0.0
    assert compare_levenshtein("John Smith", "Fredrick Smith") < 0.5
