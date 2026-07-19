from nomenklatura.matching.erun.dob import dob_match, dob_year_match

from ..factory import e


def test_dob_match_handles_exact_and_day_month_inverted_dates():
    exact = e("Person", birthDate="1952-10-07")
    inverted = e("Person", birthDate="1952-07-10")
    different = e("Person", birthDate="1952-05-01")

    assert dob_match(exact, exact) == 1.0
    assert dob_match(inverted, exact) == 0.5
    assert dob_match(exact, different) == 0.0
    assert dob_match(exact, e("Person")) == 0.0


def test_dob_year_match_distinguishes_agreement_and_conflict():
    query = e("Person", birthDate="1952-10-07")

    assert dob_year_match(query, e("Person", birthDate="1952")) == 1.0
    assert dob_year_match(query, e("Person", birthDate="1962")) == -1.0
    assert dob_year_match(query, e("Person")) == 0.0
    assert dob_year_match(e("Company"), e("Company")) == 0.0
