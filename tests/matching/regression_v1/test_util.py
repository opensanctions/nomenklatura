from nomenklatura.matching.regression_v1.util import compare_levenshtein
from nomenklatura.matching.regression_v1.util import tokenize
from nomenklatura.matching.regression_v1.util import tokenize_pair


def test_tokenize_normalizes_text_and_drops_short_tokens():
    assert tokenize(["An ACME GmbH", "Acme Société"]) == {
        "acme",
        "gmbh",
        "societe",
    }


def test_tokenize_pair_keeps_the_sides_separate():
    left, right = tokenize_pair((["Alpha Company"], ["Beta Company"]))

    assert left == {"alpha", "company"}
    assert right == {"beta", "company"}


def test_compare_levenshtein_has_stable_boundaries():
    assert compare_levenshtein("alpha", "alpha") == 1.0
    assert compare_levenshtein("alpha", "alphx") == 0.8
    assert compare_levenshtein("alpha", "omega") < 0.5
    assert compare_levenshtein("", "") == 1.0
