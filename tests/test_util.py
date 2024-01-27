from nomenklatura.util import metaphone_token


def test_phonetic():
    assert metaphone_token("Vladimir") == "FLTMR"
    assert metaphone_token("Vladimyr") == "FLTMR"
