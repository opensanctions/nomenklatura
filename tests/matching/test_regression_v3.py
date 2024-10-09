from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import RegressionV3
from nomenklatura.matching.regression_v3.names import name_match

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


POS_ET = {
    "id": "et-1",
    "schema": "Position",
    "properties": {
        "name": ["Minister of ABC"],
        "country": ["et"],
    },
}

POS_ET2 = {
    "id": "et-2",
    "schema": "Position",
    "properties": {
        "name": ["Their excellency the Minister of ABC"],
        "country": ["et"],
    },
}

POS_VU = {
    "id": "vu-1",
    "schema": "Position",
    "properties": {
        "name": ["Minister of ABC"],
        "country": ["vu"],
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


def test_position_country():
    """
    Two names matching with country mismatch should score better than two countries
    matching with name mismatch
    """
    et1 = Entity.from_dict(model, POS_ET)
    et2 = Entity.from_dict(model, POS_ET2)
    vu1 = Entity.from_dict(model, POS_VU)

    res_et1_et2 = RegressionV3.compare(et1, et2)
    res_et1_vu1 = RegressionV3.compare(et1, vu1)
    assert res_et1_et2.score > res_et1_vu1.score, (res_et1_et2, res_et1_vu1)
    assert res_et1_et2.score > 0.3, res_et1_et2
    assert res_et1_vu1.score < 0.2, res_et1_vu1


def test_name_country():
    """name and country together shouldn't be too strong"""

    data = {
        "id": "mike1",
        "schema": "Person",
        "properties": {
            "name": ["Mykhailov Hlib Leonidovych"],
            "country": ["ru"],
        },
    }
    e1 = Entity.from_dict(model, data)
    data["id"] = "mike2"
    e2 = Entity.from_dict(model, data)
    res = RegressionV3.compare(e1, e2)
    assert 0.92 < res.score < 0.95, res


def test_name_match():
    data = {
        "id": "mike1",
        "schema": "Person",
        "properties": {
            "name": [
                "John",
            ],
        },
    }
    e1 = Entity.from_dict(model, data)
    data["id"] = "mike2"
    e2 = Entity.from_dict(model, data)
    assert 0.72 < name_match(e1, e2) < 0.73

    e1.set("name", ["a" * 100])
    e2.set("name", ["a" * 100])
    assert 0.86 < name_match(e1, e2) < 0.87

    e1.set("name", [])
    e2.set("name", [])
    for i in range(10):
        char = chr(65 + i)
        e1.add("name", char * 100)
        e2.add("name", char * 100)
    assert 1.0 == name_match(e1, e2)


def test_name_address():

    a = Entity.from_dict(
        model,
        {
            "id": "a",
            "schema": "Company",
            "properties": {
                "name": ["The AAA Weapons and MunitionS Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    b = Entity.from_dict(
        model,
        {
            "id": "b",
            "schema": "Company",
            "properties": {
                "name": ["The BBB Weapons and MunitionS Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    c = Entity.from_dict(
        model,
        {
            "id": "c",
            "schema": "Company",
            "properties": {
                "name": ["The AAA Weapons and MunitioN Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    ac = RegressionV3.compare(a, c)
    assert 0.87 < ac.score < 0.93
    ab = RegressionV3.compare(a, b)
    assert 0.87 < ab.score < 0.93
    bc = RegressionV3.compare(b, c)
    assert 0.84 < bc.score < 0.93

def test_isin():
    """name and country together shouldn't be too strong"""

    data = {
        "id": "isin-123456789",
        "schema": "Security",
        "properties": {
            "name": ["Foobar Exo Something EXC A"],
            "isin": ["123456789"],
        },
    }
    e1 = Entity.from_dict(model, data)
    data["properties"]["name"] = ["Foobar Exo Something EXC B"]
    e2 = Entity.from_dict(model, data)
    data["id"] = "isin-987654321"
    data["properties"]["isin"] = ["987654321"]
    e3 = Entity.from_dict(model, data)
    res_e1_e2 = RegressionV3.compare(e1, e2)
    res_e2_e3 = RegressionV3.compare(e2, e3)
    assert res_e1_e2.score > res_e2_e3.score, (res_e1_e2, res_e2_e3)
    assert res_e1_e2.score > 0.5, res_e1_e2
    assert res_e2_e3.score < 0.5, res_e2_e3


def test_false_positive():
    """
    Regression test for false positive where last name differs
    """
    data1 = {
        "id": "mike1",
        "schema": "Person",
        "properties": {
            "name": [
                "CHUDAKOV, Vladimir Vladimirovich",
                "Vladimir Vladimirovich Chudakov",
            ],
            "alias": [
                "Uladzimiravich Uladzimir Chudakou",
                "Уладзіміравіч Уладзімір Чудакоў",
            ],
            "firstName": ["Uladzimiravich", "Vladimir", "Владимир", "Уладзіміравіч"],
            "lastName": ["Chudakou", "Chudakov", "Чудаков", "Чудакоў"],
            "country": ["by"],
        },
    }
    data2 = {
        "id": "mike2",
        "schema": "Person",
        "properties": {
            "name": ["Kachanau Uladzimir Uladzimiravich"],
            "alias": [
                "Kachanov Vladimir Vladimirovich",
                "КАЧАНАУ Уладзімір Уладзіміравіч",
                "КАЧАНОВ Владимир Владимирович",
            ],
            "firstName": ["Uladzimir", "Vladimir", "Владимир", "Уладзімір"],
            "lastName": ["Kachanau", "Kachanov", "КАЧАНАУ", "КАЧАНОВ"],
            "fatherName": [
                "Uladzimiravic", "Vladimirovich", "Владимирович", "Уладзіміравіч",
            ],
            "country": ["by"],
        },
    }
    e1 = Entity.from_dict(model, data1)
    e2 = Entity.from_dict(model, data2)
    res = RegressionV3.compare(e1, e2)
    assert res.score < 0.9, res
