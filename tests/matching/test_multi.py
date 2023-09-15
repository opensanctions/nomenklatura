from nomenklatura.matching.compare.multi import numbers_mismatch

from .util import e


def test_entity_numbers_mismatch():
    query = e("Company", name="155 machine repair plant")
    match = e("Company", name="175 machine repair plant")
    assert numbers_mismatch(query, match) == 1.0

    match = e("Company", name="175 machine repair plant, 1975")
    assert numbers_mismatch(query, match) == 1.0


def test_address_numbers_mismatch():
    query = e("Address", full="155 main st, ny 18372")
    match = e("Address", full="155 main st, ny 18372")
    assert numbers_mismatch(query, match) == 0.0

    match = e("Address", full="155 main st, ny 18382")
    assert numbers_mismatch(query, match) == 0.5

    match = e("Address", full="155 main st, ny 18382, nw 3")
    assert numbers_mismatch(query, match) == 0.5
