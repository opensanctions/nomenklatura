from nomenklatura.matching.compare.addresses import address_entity_match

from .util import e


def test_address_entity_match():
    left = e("Address", full="123 Main St, Springfield, IL")
    match = e("Address", full="Main St 123, Springfield, IL")
    assert address_entity_match(left, match) == 1.0

    # subsets are matches:
    match = e("Address", full="Main St, Springfield, IL")
    assert address_entity_match(left, match) == 1.0

    # different numbers are imperfect matches:
    match = e("Address", full="Main St 211, Springfield, IL")
    assert address_entity_match(left, match) < 1.0
    assert address_entity_match(left, match) > 0.5

    mis_match = e("Address", full="456 Elm St, Springfield, IL")
    assert address_entity_match(left, mis_match) > 0.0
    assert address_entity_match(left, mis_match) < 0.7
    mis_match = e("Address", full="Harry")
    assert address_entity_match(left, mis_match) == 0.0
    no_value = e("Address")
    assert address_entity_match(left, no_value) == 0.0
