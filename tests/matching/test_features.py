from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import compare_scored, explain_matcher

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
    explanation = explain_matcher()
    assert len(explanation) > 3, explanation
    for _, desc in explanation.items():
        assert len(desc["description"]) > 0, desc
        assert desc["coefficient"] != 0.0, desc
        assert "github" in desc["url"], desc


def test_compare_entities():
    cand = Entity.from_dict(model, candidate)
    match = Entity.from_dict(model, putin)
    mismatch = Entity.from_dict(model, saddam)

    res_match = compare_scored(cand, match)
    res_mismatch = compare_scored(cand, mismatch)
    assert res_match["score"] > res_mismatch["score"]
    assert res_match["score"] > 0.5
    assert res_mismatch["score"] < 0.5


def test_compare_features():
    cand = Entity.from_dict(model, candidate)
    match = Entity.from_dict(model, putin)
    ref_match = compare_scored(cand, match)
    ref_score = ref_match["score"]

    no_bday = match.clone()
    no_bday.pop("birthDate")
    bday_match = compare_scored(cand, no_bday)
    assert ref_score > bday_match["score"]

    bela = match.clone()
    bela.set("nationality", "by")
    bela_match = compare_scored(cand, bela)
    assert ref_score > bela_match["score"]
