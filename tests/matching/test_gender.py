from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_gender_mismatch():
    left = e("Person", gender="female")
    match = e("Person", gender="female")
    assert gender_mismatch(left, match, config).score == 0.0
    mis_match = e("Person", gender="male")
    assert gender_mismatch(left, mis_match, config).score == 1.0
    no_value = e("Person", name="Harry")
    assert gender_mismatch(left, no_value, config).score == 0.0
