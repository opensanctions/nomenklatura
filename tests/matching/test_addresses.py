from nomenklatura.matching.compare.addresses import address_entity_match
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_address_entity_match():
    left = e("Address", full="123 Main St, Springfield, IL")
    match = e("Address", full="Main St 123, Springfield, IL")
    assert address_entity_match(left, match, config).score == 1.0

    # subsets are matches:
    match = e("Address", full="Main St, Springfield, IL")
    assert address_entity_match(left, match, config).score == 1.0

    # different numbers are imperfect matches:
    match = e("Address", full="Main St 211, Springfield, IL")
    assert address_entity_match(left, match, config).score < 1.0
    assert address_entity_match(left, match, config).score > 0.5

    mis_match = e("Address", full="456 Elm St, Springfield, IL")
    assert address_entity_match(left, mis_match, config).score > 0.0
    assert address_entity_match(left, mis_match, config).score < 0.7
    mis_match = e("Address", full="Harry")
    assert address_entity_match(left, mis_match, config).score == 0.0
    no_value = e("Address")
    assert address_entity_match(left, no_value, config).score == 0.0
