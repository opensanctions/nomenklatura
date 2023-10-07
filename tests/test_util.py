from nomenklatura.util import is_qid, normalize_url
from nomenklatura.util import levenshtein_similarity
from nomenklatura.util import metaphone_token


def test_is_qid():
    assert is_qid("Q7747")
    assert not is_qid("q7747")
    assert not is_qid("Q7747B")
    assert not is_qid("banana")


def test_normalize_url():
    assert normalize_url("http://pudo.org") == "http://pudo.org"
    assert normalize_url("http://pudo.org/blub") == "http://pudo.org/blub"
    assert normalize_url("http://pudo.org", {"q": "bla"}) == "http://pudo.org?q=bla"
    assert normalize_url("http://pudo.org", [("q", "bla")]) == "http://pudo.org?q=bla"
    assert (
        normalize_url("http://pudo.org?t=1", {"q": "bla"})
        == "http://pudo.org?t=1&q=bla"
    )


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
