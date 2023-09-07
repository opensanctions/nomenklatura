from nomenklatura.matching.compare.countries import country_mismatch

from .util import e


def test_country_mismatch():
    left = e("Person", country="ua")
    match = e("Person", country="ua")
    assert country_mismatch(left, match) == 0.0
    mis_match = e("Person", country="ru")
    assert country_mismatch(left, mis_match) == 1.0
    no_value = e("Person", name="Harry")
    assert country_mismatch(left, no_value) == 0.0
