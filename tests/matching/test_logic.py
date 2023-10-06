from nomenklatura.matching import LogicV1
from nomenklatura.matching.compare.names import name_literal_match
from nomenklatura.matching.compare.phonetic import name_metaphone_match

from .util import e


def test_logic_scoring():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b).score == 1.0
    b = e("Person", name="Vladimir Pudin")
    assert LogicV1.compare(a, b).score < 1.0
    assert LogicV1.compare(a, b).score > 0.7


def test_logic_overrides():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    result = LogicV1.compare(a, b, {})
    assert result.score == 1.0
    assert name_literal_match.__name__ in result.features
    assert name_metaphone_match.__name__ not in result.features
    overrides = {
        name_literal_match.__name__: 0.0,
        name_metaphone_match.__name__: 0.96,
    }
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    result = LogicV1.compare(a, b, overrides)
    assert result.score < 1.0
    assert name_literal_match.__name__ not in result.features
    assert name_metaphone_match.__name__ in result.features
    assert result.features[name_metaphone_match.__name__] == 1.0


def test_logic_qualified_country():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b).score == 1.0
    a.add("country", "pa")
    b.add("country", "ru")
    assert LogicV1.compare(a, b).score > 0.7
    assert LogicV1.compare(a, b).score < 0.9


def test_logic_qualified_dob():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b).score == 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1952-05-01")
    assert LogicV1.compare(a, b).score > 0.7
    assert LogicV1.compare(a, b).score < 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1962-05-01")
    assert LogicV1.compare(a, b).score > 0.5
    assert LogicV1.compare(a, b).score < 0.7


def test_logic_legal_entity():
    a = e("LegalEntity", name="CRYSTALORD LTD")
    b = e("LegalEntity", name="CRYSTALORD LTD")
    assert LogicV1.compare(a, b).score == 1.0


def test_logic_qualified_corp():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    assert LogicV1.compare(a, b).score == 1.0
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "748745")
    assert LogicV1.compare(a, b).score == 0.8
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "E137332")
    assert LogicV1.compare(a, b).score > 0.9


def test_logic_id_only_corp():
    a = e("Company", name="OTHER LTD", registrationNumber="77401103")
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    assert LogicV1.compare(a, b).score > 0.7, LogicV1.compare(a, b).features
    assert LogicV1.compare(a, b).score < 0.9


def test_imo_match():
    query = e("Vessel", imoNumber="IMO 9929429", country="lr")
    result = e("Vessel", imoNumber="IMO 9929429")
    imo_match = LogicV1.compare(query, result).score
    assert imo_match > 0.7

    result = e("Vessel", imoNumber="9929429", country="ru")
    imo_match_mis = LogicV1.compare(query, result).score
    assert imo_match > imo_match_mis
    assert imo_match_mis > 0.7


def test_logic_id_disjoint():
    a = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    assert LogicV1.compare(a, b).score == 1.0
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="379483787")
    assert LogicV1.compare(a, b).score < 1.0
    assert LogicV1.compare(a, b).score > 0.7


def test_logic_different_country():
    a = e("Company", name="CRYSTALORD LTD", country="pa")
    b = e("Company", name="CRYSTALORD LTD", country="pa")
    assert LogicV1.compare(a, b).score == 1.0
    b = e("Company", name="CRYSTALORD LTD", country="us")
    assert LogicV1.compare(a, b).score < 1.0
    assert LogicV1.compare(a, b).score > 0.7


def test_qualifiers_progression():
    result = e(
        "Person",
        name="Alexandre Boris de Pfeffel Johnson",
        birthDate="1964-06-19",
        nationality="gb",
        gender="male",
    )
    query = e("Person", name="Boris Johnson")
    name_only = LogicV1.compare(query, result).score
    assert name_only > 0.5
    assert name_only < 1.0

    query = e("Person", name="Boris Johnson", birthDate="1964-06-19")
    name_dob = LogicV1.compare(query, result).score
    assert name_dob == name_only

    query = e("Person", name="Boris Johnson", birthDate="1967")
    name_dob = LogicV1.compare(query, result).score
    assert name_dob < name_only

    query = e("Person", name="Boris Johnson", gender="female")
    name_gender = LogicV1.compare(query, result).score
    assert name_gender < name_only

    query = e("Person", name="Geoffrey Boris Johnson")
    name_extra = LogicV1.compare(query, result).score
    assert name_extra < name_only

    query = e("Person", name="Boris de Pfeffel Johnson", nationality="tr")
    name_nat = LogicV1.compare(query, result).score
    assert name_nat < 1.0
    assert name_nat > 0.5
