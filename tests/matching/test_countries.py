from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_country_mismatch():
    left = e("Person", country="ua")
    match = e("Person", country="ua")
    assert country_mismatch(left, match, config).score == 0.0
    mis_match = e("Person", country="ru")
    assert country_mismatch(left, mis_match, config).score == 1.0
    no_value = e("Person", name="Harry")
    assert country_mismatch(left, no_value, config).score == 0.0
