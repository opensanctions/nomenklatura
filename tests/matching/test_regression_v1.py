from followthemoney import StatementEntity as Entity

from nomenklatura.matching import RegressionV1
from nomenklatura.matching.types import ScoringConfig

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
