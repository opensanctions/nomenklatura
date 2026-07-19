import numpy as np

from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.types import ScoringConfig

from ..factory import e


config = ScoringConfig.defaults()


def score(query, result) -> float:
    return EntityResolveRegression.compare(query, result, config).score


def test_person_name_contract_orders_exact_typo_and_unrelated_names():
    # The typo and unrelated examples are copied from the strong name benchmark
    # cases, but remain local so erun owns its expected ordering.
    query = e("Person", name="Vladimir Putin")
    exact = e("Person", name="Vladimir Putin")
    typo = e("Person", name="Vladimir Pulin")
    unrelated = e("Person", name="Usama bin Laden")
    other = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")

    exact_score = score(query, exact)
    typo_score = score(query, typo)
    unrelated_score = score(unrelated, other)

    assert 0.0 <= unrelated_score < typo_score < exact_score <= 1.0


def test_company_name_contract_prefers_legal_form_variants():
    # Copied from contrib/entity_bench/checks.yml.
    siemens = e("Company", name="Siemens Aktiengesellschaft")
    legal_form_variant = e("Company", name="Siemens AG")
    unrelated = e("Company", name="Volkswagen Aktiengesellschaft")

    assert score(siemens, legal_form_variant) > score(unrelated, siemens)


def test_conflicting_qualifiers_reduce_an_exact_name_match():
    query = e(
        "Person",
        name="Vladimir Putin",
        birthDate="1952-10-07",
        country="ru",
    )
    consistent = e(
        "Person",
        name="Vladimir Putin",
        birthDate="1952-10-07",
        country="ru",
    )
    conflicting = e(
        "Person",
        name="Vladimir Putin",
        birthDate="1962-10-07",
        country="us",
    )

    assert score(query, consistent) > score(query, conflicting)


def test_matching_identifier_rescues_unrelated_company_names():
    query = e("Company", name="OTHER LTD", leiCode="1595VL9OPPQ5THEK2X30")
    with_identifier = e(
        "Company", name="CRYSTALORD LTD", leiCode="1595VL9OPPQ5THEK2X30"
    )
    without_identifier = e("Company", name="CRYSTALORD LTD")

    assert score(query, with_identifier) > score(query, without_identifier)


def test_encoded_features_align_with_the_packaged_model():
    query = e("Person", name="Vladimir Putin", birthDate="1952-10-07")
    result = e("Person", name="Vladimir Pulin", birthDate="1952")

    encoded = EntityResolveRegression.encode_pair(query, result)
    _, coefficients = EntityResolveRegression.load()

    assert len(encoded) == len(EntityResolveRegression.FEATURES)
    assert list(coefficients) == [
        feature.__name__ for feature in EntityResolveRegression.FEATURES
    ]
    assert np.isfinite(encoded).all()


def test_dedupe_scores_are_symmetric():
    pairs = [
        (
            e("Person", name="Vladimir Putin", country="ru"),
            e("Person", name="Vladimir Pulin", country="us"),
        ),
        (
            e("Company", name="Siemens Aktiengesellschaft"),
            e("Company", name="Siemens AG"),
        ),
        (
            e("Company", name="OTHER LTD", leiCode="1595VL9OPPQ5THEK2X30"),
            e(
                "Company",
                name="CRYSTALORD LTD",
                registrationNumber="1595VL9OPPQ5THEK2X30",
            ),
        ),
        (
            e("Company", address="12 Main Street, Berlin"),
            e("Company", address="Main Street, Berlin"),
        ),
    ]

    for left, right in pairs:
        assert score(left, right) == score(right, left)
