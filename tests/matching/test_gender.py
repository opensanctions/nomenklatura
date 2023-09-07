from nomenklatura.matching.compare.gender import gender_mismatch

from .util import e


def test_gender_mismatch():
    left = e("Person", gender="female")
    match = e("Person", gender="female")
    assert gender_mismatch(left, match) == 0.0
    mis_match = e("Person", gender="male")
    assert gender_mismatch(left, mis_match) == 1.0
    no_value = e("Person", name="Harry")
    assert gender_mismatch(left, no_value) == 0.0
