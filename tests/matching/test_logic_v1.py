from nomenklatura.matching import LogicV1
from nomenklatura.matching.compare.names import name_literal_match
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.logic_v1.phonetic import name_metaphone_match
from nomenklatura.matching.logic_v1.phonetic import person_name_phonetic_match
from nomenklatura.matching.logic_v1.phonetic import name_soundex_match
from nomenklatura.matching.logic_v1.phonetic import metaphone_token
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_phonetic():
    assert metaphone_token("Vladimir") == "FLTMR"
    assert metaphone_token("Vladimyr") == "FLTMR"


def test_logic_scoring():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b, config).score == 1.0
    b = e("Person", name="Vladimir Pudin")
    assert LogicV1.compare(a, b, config).score < 1.0
    assert LogicV1.compare(a, b, config).score > 0.7


def test_logic_overrides():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    config = ScoringConfig.defaults()
    result = LogicV1.compare(a, b, config)
    assert result.score == 1.0
    assert name_literal_match.__name__ in result.features
    assert name_metaphone_match.__name__ not in result.features
    overrides = {
        name_literal_match.__name__: 0.0,
        name_metaphone_match.__name__: 0.96,
    }
    config = ScoringConfig(weights=overrides, config={})
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    result = LogicV1.compare(a, b, config)
    assert result.score < 1.0
    assert name_literal_match.__name__ not in result.features
    assert name_metaphone_match.__name__ in result.features
    assert result.features[name_metaphone_match.__name__] == 1.0


def test_logic_qualified_country():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b, config).score == 1.0
    a.add("country", "pa")
    b.add("country", "ru")
    assert LogicV1.compare(a, b, config).score > 0.7
    assert LogicV1.compare(a, b, config).score < 0.9


def test_logic_qualified_dob():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert LogicV1.compare(a, b, config).score == 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1952-05-01")
    assert LogicV1.compare(a, b, config).score > 0.7
    assert LogicV1.compare(a, b, config).score < 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1962-05-01")
    assert LogicV1.compare(a, b, config).score > 0.5
    assert LogicV1.compare(a, b, config).score < 0.7


def test_logic_legal_entity():
    a = e("LegalEntity", name="CRYSTALORD LTD")
    b = e("LegalEntity", name="CRYSTALORD LTD")
    assert LogicV1.compare(a, b, config).score == 1.0


def test_logic_qualified_corp():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    assert LogicV1.compare(a, b, config).score == 1.0
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "748745")
    assert LogicV1.compare(a, b, config).score == 0.8
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "E137332")
    assert LogicV1.compare(a, b, config).score > 0.9


def test_logic_id_only_corp():
    a = e("Company", name="OTHER LTD", registrationNumber="77401103")
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    result = LogicV1.compare(a, b, config)
    assert result.score > 0.7, result.features
    assert result.score < 0.9


def test_imo_match():
    query = e("Vessel", imoNumber="IMO 9929429", country="lr")
    result = e("Vessel", imoNumber="IMO 9929429")
    imo_match = LogicV1.compare(query, result, config).score
    assert imo_match > 0.7

    result = e("Vessel", imoNumber="9929429", country="ru")
    imo_match_mis = LogicV1.compare(query, result, config).score
    assert imo_match > imo_match_mis
    assert imo_match_mis > 0.7


def test_logic_id_disjoint():
    a = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="77401103")
    assert LogicV1.compare(a, b, config).score == 1.0
    b = e("Company", name="CRYSTALORD LTD", registrationNumber="379483787")
    assert LogicV1.compare(a, b, config).score < 1.0
    assert LogicV1.compare(a, b, config).score > 0.7


def test_logic_different_country():
    a = e("Company", name="CRYSTALORD LTD", country="pa")
    b = e("Company", name="CRYSTALORD LTD", country="pa")
    assert LogicV1.compare(a, b, config).score == 1.0
    b = e("Company", name="CRYSTALORD LTD", country="us")
    assert LogicV1.compare(a, b, config).score < 1.0
    assert LogicV1.compare(a, b, config).score > 0.7


def test_qualifiers_progression():
    result = e(
        "Person",
        name="Alexandre Boris de Pfeffel Johnson",
        birthDate="1964-06-19",
        nationality="gb",
        gender="male",
    )
    query = e("Person", name="Boris Johnson")
    name_only = LogicV1.compare(query, result, config).score
    assert name_only > 0.5
    assert name_only < 1.0

    query = e("Person", name="Boris Johnson", birthDate="1964-06-19")
    name_dob = LogicV1.compare(query, result, config).score
    assert name_dob == name_only

    query = e("Person", name="Boris Johnson", birthDate="1967")
    name_dob = LogicV1.compare(query, result, config).score
    assert name_dob < name_only

    query = e("Person", name="Boris Johnson", gender="female")
    name_gender = LogicV1.compare(query, result, config).score
    assert name_gender < name_only

    query = e("Person", name="Geoffrey Boris Johnson")
    name_extra = LogicV1.compare(query, result, config).score
    assert name_extra < name_only

    query = e("Person", name="Boris de Pfeffel Johnson", nationality="tr")
    name_nat = LogicV1.compare(query, result, config).score
    assert name_nat < 1.0
    assert name_nat > 0.5


def test_person_name_phonetic_match():
    query = e("Company", name="Michaela Michelle Micheli")
    result = e("Company", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result) == 0.0
    assert name_metaphone_match(query, result) > 0.5
    assert name_metaphone_match(query, result) < 1.0
    assert name_soundex_match(query, result) > 0.5
    assert name_soundex_match(query, result) < 1.0

    query = e("Company", name="OAO Gazprom")
    result = e("Company", name="Open Joint Stock Company Gazprom")
    assert name_metaphone_match(query, result) == 1.0
    assert name_soundex_match(query, result) == 1.0

    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert person_name_phonetic_match(query, result) == 1.0
    assert name_metaphone_match(query, result) == 1.0
    assert name_soundex_match(query, result) == 1.0

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_phonetic_match(query, result) > 0.5

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michell Obama")
    assert person_name_phonetic_match(query, result) > 0.3
    assert person_name_phonetic_match(query, result) < 0.7
    assert name_metaphone_match(query, result) > 0.0
    assert name_metaphone_match(query, result) < 0.5
    assert name_soundex_match(query, result) > 0.0
    assert name_soundex_match(query, result) < 0.5

    query = e("Person", name="Barack Obama")
    result = e("Person", name="George Hussein Onyango Obama")
    assert person_name_phonetic_match(query, result) < 0.7
    result = e("Person", name="Բարակ Օբամա")
    assert person_name_phonetic_match(query, result) > 0.7
    result = e("Person", name="ジョージ")
    assert person_name_phonetic_match(query, result) < 0.7
    result = e("Person", name="Marie-Therese Abena Ondoa")
    assert person_name_phonetic_match(query, result) < 0.7
    result = e("Person", name="ماري تيريز أدينا أوندوا")
    assert person_name_phonetic_match(query, result) < 0.7

    query = e("Person", name="Vita Klave")
    result = e("Person", name="Фуад Гулієв")
    assert person_name_phonetic_match(query, result) < 1.0

    query = e("Person", name="Olga Barynova")
    result = e("Person", name="Oleg BARANOV")
    assert person_name_phonetic_match(query, result) < 0.6

    query = e("Person", name="Ginta Boreza")
    result = e("Person", name="Janett Borez")
    assert person_name_phonetic_match(query, result) < 0.6

    query = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    result = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result) == 1.0
    query = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result) == 1.0

    query = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result) > 0.5
    query = e("Person", name="AL BIN ALI, Isa Bin Taryf")
    assert person_name_phonetic_match(query, result) == 1.0

    query = e("Person", name="AL BEN MAHMOUD, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_phonetic_match(query, result) > 0.4

    query = e("Person", name="باراك أوباما")
    result = e("Person", name="محمد بن سلمان آل سعود")
    assert person_name_phonetic_match(query, result) < 0.1


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert person_name_phonetic_match(name, other) == 1.0
    assert person_name_jaro_winkler(name, other) == 1.0

    other = e("Person", name="Hanniball")
    assert person_name_phonetic_match(name, other) == 1.0

    other = e("Person", name="Hannibol")
    assert person_name_phonetic_match(name, other) == 1.0
    assert person_name_jaro_winkler(name, other) > 0.8
    assert person_name_jaro_winkler(name, other) < 1.0


def test_name_alphabets():
    query = e("Person", name="Ротенберг Аркадий")
    result = e("Person", name="Arkadij Romanovich Rotenberg")
    # assert person_name_phonetic_match(query, result) > 0.0
    assert person_name_phonetic_match(query, result) > 0.7
    assert person_name_jaro_winkler(query, result) > 0.7

    query = e("Person", name="Osama bin Laden")
    result = e("Person", name="Usāma bin Muhammad ibn Awad ibn Lādin")
    assert person_name_phonetic_match(query, result) > 0.3
    assert person_name_phonetic_match(query, result) < 0.9
    assert person_name_jaro_winkler(query, result) > 0.5
    assert person_name_jaro_winkler(query, result) < 0.9
