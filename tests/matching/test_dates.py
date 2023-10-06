from nomenklatura.matching.compare.dates import dob_matches, dob_year_matches
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint

from .util import e


def test_dob_matches():
    left = e("Person", birthDate="1980-04-16")
    right = e("Person", birthDate="1980-04-16")
    assert dob_matches(left, right) == 1.0
    assert dob_year_matches(left, right) == 1.0
    assert dob_day_disjoint(left, right) == 0.0
    assert dob_year_disjoint(left, right) == 0.0
    right = e("Person", birthDate="1980")
    assert dob_year_matches(left, right) == 1.0
    assert dob_day_disjoint(left, right) == 0.0
    right = e("Person", birthDate="1980-04")
    assert dob_year_matches(left, right) == 1.0
    assert dob_day_disjoint(left, right) == 0.0
    right = e("Person", birthDate="1980-04-16T19:00:00")
    assert dob_matches(left, right) == 1.0
    assert dob_year_matches(left, right) == 1.0
    assert dob_day_disjoint(left, right) == 0.0
    right = e("Person", birthDate="1965-04-16")
    assert dob_matches(left, right) == 0.0
    assert dob_year_matches(left, right) == 0.0
    assert dob_day_disjoint(left, right) == 1.0
    assert dob_year_disjoint(left, right) == 1.0
    none = e("Person", name="Harry")
    assert dob_matches(left, none) == 0.0
    assert dob_year_matches(left, none) == 0.0
    assert dob_day_disjoint(left, none) == 0.0
    assert dob_year_disjoint(left, none) == 0.0
