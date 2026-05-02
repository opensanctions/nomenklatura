from typing import List
from rigour.names import CompareConfig, Name, NamePart

from nomenklatura.matching.logic_v2.names.distance import (
    weighted_edit_similarity as wes,
)
from nomenklatura.matching.logic_v2.names.distance import strict_levenshtein

CFG = CompareConfig()


def pt(name: str) -> List[NamePart]:
    return Name(name).parts


def test_weighted_similarity():
    matches = wes(pt("Vladimir Putin"), pt("Vladimir Putin"), CFG)
    assert len(matches) == 2
    assert matches[0].score == 1.0
    assert matches[1].score == 1.0
    matches = wes(pt(""), pt("Putin, Vladimir"), CFG)
    assert len(matches) == 2
    assert len(matches[0].qps) == 0
    assert len(matches[0].rps) == 1

    matches = wes(pt("Vladimir Borisovich Putin"), pt("Vladimir Putin"), CFG)
    assert len(matches) == 3
    scores = sorted([m.score for m in matches])
    assert scores == [0.0, 1.0, 1.0]

    matches = wes(pt("Putin, Vladimir"), pt("PutinVladimir"), CFG)
    assert len(matches) == 1
    assert matches[0].score < 1.0
    assert len(matches[0].qps) == 2
    assert len(matches[0].rps) == 1

    matches = wes(pt("platonovich"), pt("plat ono vich"), CFG)
    assert len(matches) == 1
    assert matches[0].score < 1.0
    assert matches[0].score > 0.8
    assert len(matches[0].qps) == 1
    assert len(matches[0].rps) == 3


def test_strict_levenshtein():
    assert strict_levenshtein("abc", "abc") == 1.0
    assert strict_levenshtein("abc", "ab") == 0.0
    assert strict_levenshtein("hello", "hello") == 1.0
    assert strict_levenshtein("hello", "hullo") > 0.0
    assert strict_levenshtein("hello", "hullo") < 1.0


def test_weighted_edit_similarity_manjit_manjeet():
    # Default tolerance (1.0) keeps the cluster above zero.
    matches = wes(pt("Manjit"), pt("Manjeet"), CFG)
    assert 0.6 < matches[0].score < 0.7

    # Stricter tolerance (0.9) hits the budget cliff and zeroes the cluster.
    strict = CompareConfig(budget_tolerance=0.9)
    matches = wes(pt("Manjit"), pt("Manjeet"), strict)
    assert matches[0].score == 0.0

