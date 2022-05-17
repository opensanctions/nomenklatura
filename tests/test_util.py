from nomenklatura.util import is_qid, normalize_url


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
