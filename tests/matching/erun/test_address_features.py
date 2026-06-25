from banal import ensure_list
from followthemoney import EntityProxy

from nomenklatura.matching.erun.misc import (
    address_number_disagreement,
    address_number_overlap,
)


def entity(*addresses: str) -> EntityProxy:
    return EntityProxy.from_dict(
        {
            "id": "entity",
            "schema": "Company",
            "properties": {"address": ensure_list(addresses)},
        }
    )


def test_address_number_features_are_symmetric_and_bounded() -> None:
    left = entity("12 Main Street", "34 Second Street")
    right = entity("Main Street 12")

    assert address_number_overlap(left, right) == 1.0
    assert address_number_overlap(right, left) == 1.0
    assert address_number_disagreement(left, right) == 0.5
    assert address_number_disagreement(right, left) == 0.5


def test_address_number_features_separate_disagreement_and_missingness() -> None:
    left = entity("12 Main Street")
    different = entity("34 Main Street")
    missing = entity("Main Street")

    assert address_number_overlap(left, different) == 0.0
    assert address_number_disagreement(left, different) == 1.0
    assert address_number_overlap(left, missing) == 0.0
    assert address_number_disagreement(left, missing) == 0.0
