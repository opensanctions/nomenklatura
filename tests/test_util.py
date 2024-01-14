from nomenklatura.util import levenshtein_similarity
from nomenklatura.util import metaphone_token


def test_compare_levenshtein():
    assert levenshtein_similarity("John Smith", "John Smith") == 1.0
    johnny = levenshtein_similarity("John Smith", "Johnny Smith")
    assert johnny < 1.0
    assert johnny > 0.5
    johnathan = levenshtein_similarity("John Smith", "Johnathan Smith")
    assert johnathan < 1.0
    assert johnathan > 0.0
    assert levenshtein_similarity("John Smith", "Fredrick Smith") < 0.5


def test_phonetic():
    assert metaphone_token("Vladimir") == "FLTMR"
    assert metaphone_token("Vladimyr") == "FLTMR"
