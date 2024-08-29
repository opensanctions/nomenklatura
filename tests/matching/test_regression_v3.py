from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import RegressionV3

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

NAME1_ADDR1 = {
    "id": "e1-a1",
    "schema": "LegalEntity",
    "properties": {
        "name": ["ACME Manufacturing"],
        "address": ["123 Fake St, Springfield, 91210, USA"],
    },
}

NAME1_ADDR2 = {
    "id": "e1-a2",
    "schema": "LegalEntity",
    "properties": {
        "name": ["ACME Manufacturing"],
        "address": ["456 Real Street, Kashmir, 987654, Pakistan"],
    },
}

NAME2_ADDR1 = {
    "id": "e2-a1",
    "schema": "LegalEntity",
    "properties": {
        "name": ["John Smith"],
        "address": ["123 Fake St, Springfield, 91210, USA"],
    },
}


def test_explain_matcher():
    explanation = RegressionV3.explain()
    assert len(explanation) > 3, explanation
    for _, desc in explanation.items():
        assert len(desc.description) > 0, desc
        assert desc.coefficient != 0.0, desc
        assert "github" in desc.url, desc


def test_compare_entities():
    cand = Entity.from_dict(model, candidate)
    match = Entity.from_dict(model, putin)
    mismatch = Entity.from_dict(model, saddam)

    res_match = RegressionV3.compare(cand, match)
    res_mismatch = RegressionV3.compare(cand, mismatch)
    assert res_match.score > res_mismatch.score
    assert res_match.score > 0.5
    assert res_mismatch.score < 0.5


def test_compare_features():
    cand = Entity.from_dict(model, candidate)
    match = Entity.from_dict(model, putin)
    ref_match = RegressionV3.compare(cand, match)
    ref_score = ref_match.score

    no_bday = match.clone()
    no_bday.pop("birthDate")
    bday_match = RegressionV3.compare(cand, no_bday)
    assert ref_score > bday_match.score

    bela = match.clone()
    bela.set("nationality", "by")
    bela_match = RegressionV3.compare(cand, bela)
    assert ref_score > bela_match.score


def test_legal_entity_address_match():
    name1_addr1 = Entity.from_dict(model, NAME1_ADDR1)
    name1_addr2 = Entity.from_dict(model, NAME1_ADDR2)
    name2_addr1 = Entity.from_dict(model, NAME2_ADDR1)

    res_name_1_addr1_addr2 = RegressionV3.compare(name1_addr1, name1_addr2)
    res_name1_name2_addr1 = RegressionV3.compare(name1_addr1, name2_addr1)
    assert res_name_1_addr1_addr2.score > res_name1_name2_addr1.score
