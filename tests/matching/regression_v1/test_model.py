import numpy as np
from followthemoney import StatementEntity as Entity

from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

config = ScoringConfig.defaults()
candidate = {
    "id": "left-putin",
    "schema": "Person",
    "properties": {
        "name": ["Vladimir Putin"],
        "birthDate": ["1952-10-07"],
        "country": ["ru"],
    },
}

putin = {
    "id": "right-putin",
    "schema": "Person",
    "properties": {
        "name": ["Vladimir Vladimirovich Putin"],
        "birthDate": ["1952-10-07"],
        "nationality": ["ru"],
    },
}

saddam = {
    "id": "other-guy",
    "schema": "Person",
    "properties": {
        "name": ["Saddam Hussein"],
        "birthDate": ["1937"],
        "nationality": ["iq"],
    },
}


def test_explain_matcher():
    explanation = RegressionV1.get_feature_docs()
    assert len(explanation) > 3, explanation
    for _, desc in explanation.items():
        assert desc.description is not None
        assert len(desc.description) > 0, desc
        assert desc.coefficient != 0.0, desc
        assert "github" in desc.url, desc


def test_compare_entities():
    cand = Entity.from_dict(candidate)
    match = Entity.from_dict(putin)
    mismatch = Entity.from_dict(saddam)

    res_match = RegressionV1.compare(cand, match, config)
    res_mismatch = RegressionV1.compare(cand, mismatch, config)
    assert res_match.score > res_mismatch.score
    assert res_match.score > 0.5
    assert res_mismatch.score < 0.5


def test_compare_features():
    cand = Entity.from_dict(candidate)
    match = Entity.from_dict(putin)
    ref_match = RegressionV1.compare(cand, match, config)
    ref_score = ref_match.score

    no_bday = match.clone()
    no_bday.pop("birthDate")
    bday_match = RegressionV1.compare(cand, no_bday, config)
    assert ref_score > bday_match.score

    bela = match.clone()
    bela.set("nationality", "by")
    bela_match = RegressionV1.compare(cand, bela, config)
    assert ref_score > bela_match.score


def test_person_name_contract_orders_exact_typo_and_unrelated_names():
    # The typo and unrelated examples are copied from the strong name benchmark
    # cases, but remain local so RegressionV1 owns its expected ordering.
    query = e("Person", name="Vladimir Putin")
    exact = e("Person", name="Vladimir Putin")
    typo = e("Person", name="Vladimir Pulin")
    unrelated = e("Person", name="Usama bin Laden")
    other = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")

    exact_score = RegressionV1.compare(query, exact, config).score
    typo_score = RegressionV1.compare(query, typo, config).score
    unrelated_score = RegressionV1.compare(unrelated, other, config).score

    assert 0.0 <= unrelated_score < typo_score < exact_score <= 1.0


def test_company_name_contract_prefers_legal_form_variants():
    # Copied from contrib/entity_bench/checks.yml.
    siemens = e("Company", name="Siemens Aktiengesellschaft")
    legal_form_variant = e("Company", name="Siemens AG")
    unrelated = e("Company", name="Volkswagen Aktiengesellschaft")

    variant_score = RegressionV1.compare(siemens, legal_form_variant, config).score
    unrelated_score = RegressionV1.compare(unrelated, siemens, config).score

    assert variant_score > unrelated_score


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

    consistent_score = RegressionV1.compare(query, consistent, config).score
    conflicting_score = RegressionV1.compare(query, conflicting, config).score

    assert consistent_score > conflicting_score


def test_matching_identifier_rescues_unrelated_company_names():
    query = e("Company", name="OTHER LTD", leiCode="1595VL9OPPQ5THEK2X30")
    with_identifier = e(
        "Company", name="CRYSTALORD LTD", leiCode="1595VL9OPPQ5THEK2X30"
    )
    without_identifier = e("Company", name="CRYSTALORD LTD")

    rescued_score = RegressionV1.compare(query, with_identifier, config).score
    name_only_score = RegressionV1.compare(query, without_identifier, config).score

    assert rescued_score > name_only_score


def test_encoded_features_align_with_the_packaged_model():
    query = e("Person", name="Vladimir Putin", birthDate="1952-10-07")
    result = e("Person", name="Vladimir Pulin", birthDate="1952")

    encoded = RegressionV1.encode_pair(query, result)
    _, coefficients = RegressionV1.load()

    assert len(encoded) == len(RegressionV1.FEATURES)
    assert list(coefficients) == [feature.__name__ for feature in RegressionV1.FEATURES]
    assert np.isfinite(encoded).all()
