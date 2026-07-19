from nomenklatura.matching.logic_v1.phonetic import metaphone_token
from nomenklatura.matching.logic_v1.phonetic import name_metaphone_match
from nomenklatura.matching.logic_v1.phonetic import name_soundex_match
from nomenklatura.matching.logic_v1.phonetic import person_name_phonetic_match
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

config = ScoringConfig.defaults()


def test_phonetic():
    assert metaphone_token("Vladimir") == "FLTMR"
    assert metaphone_token("Vladimyr") == "FLTMR"


def test_person_name_phonetic_match():
    query = e("Company", name="Michaela Michelle Micheli")
    result = e("Company", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result, config).score == 0.0
    assert name_metaphone_match(query, result, config).score > 0.5
    assert name_metaphone_match(query, result, config).score < 1.0
    assert name_soundex_match(query, result, config).score > 0.5
    assert name_soundex_match(query, result, config).score < 1.0

    query = e("Company", name="OAO Gazprom")
    result = e("Company", name="Open Joint Stock Company Gazprom")
    assert name_metaphone_match(query, result, config).score == 1.0
    assert name_soundex_match(query, result, config).score == 1.0

    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert person_name_phonetic_match(query, result, config).score == 1.0
    assert name_metaphone_match(query, result, config).score == 1.0
    assert name_soundex_match(query, result, config).score == 1.0

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result, config).score < 1.0
    assert person_name_phonetic_match(query, result, config).score > 0.5

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michell Obama")
    assert person_name_phonetic_match(query, result, config).score > 0.3
    assert person_name_phonetic_match(query, result, config).score < 0.7
    assert name_metaphone_match(query, result, config).score > 0.0
    assert name_metaphone_match(query, result, config).score < 0.5
    assert name_soundex_match(query, result, config).score > 0.0
    assert name_soundex_match(query, result, config).score < 0.5

    query = e("Person", name="Barack Obama")
    result = e("Person", name="George Hussein Onyango Obama")
    assert person_name_phonetic_match(query, result, config).score < 0.7
    result = e("Person", name="Բարակ Օբամա")
    assert person_name_phonetic_match(query, result, config).score > 0.7
    result = e("Person", name="ジョージ")
    assert person_name_phonetic_match(query, result, config).score < 0.7
    result = e("Person", name="Marie-Therese Abena Ondoa")
    assert person_name_phonetic_match(query, result, config).score < 0.7
    result = e("Person", name="ماري تيريز أدينا أوندوا")
    assert person_name_phonetic_match(query, result, config).score < 0.7

    query = e("Person", name="Vita Klave")
    result = e("Person", name="Фуад Гулієв")
    assert person_name_phonetic_match(query, result, config).score < 1.0

    query = e("Person", name="Olga Barynova")
    result = e("Person", name="Oleg BARANOV")
    assert person_name_phonetic_match(query, result, config).score < 0.6

    query = e("Person", name="Ginta Boreza")
    result = e("Person", name="Janett Borez")
    assert person_name_phonetic_match(query, result, config).score < 0.6

    query = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    result = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result, config).score == 1.0
    query = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result, config).score == 1.0

    query = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result, config).score > 0.5
    query = e("Person", name="AL BIN ALI, Isa Bin Taryf")
    assert person_name_phonetic_match(query, result, config).score == 1.0

    query = e("Person", name="AL BEN MAHMOUD, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result, config).score < 1.0
    assert person_name_phonetic_match(query, result, config).score > 0.4

    query = e("Person", name="باراك أوباما")
    result = e("Person", name="محمد بن سلمان آل سعود")
    assert person_name_phonetic_match(query, result, config).score < 0.1


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert person_name_phonetic_match(name, other, config).score == 1.0

    other = e("Person", name="Hanniball")
    assert person_name_phonetic_match(name, other, config).score == 1.0

    other = e("Person", name="Hannibol")
    assert person_name_phonetic_match(name, other, config).score == 1.0


def test_name_alphabets():
    query = e("Person", name="Ротенберг Аркадий")
    result = e("Person", name="Arkadij Romanovich Rotenberg")
    assert person_name_phonetic_match(query, result, config).score > 0.7

    query = e("Person", name="Osama bin Laden")
    result = e("Person", name="Usāma bin Muhammad ibn Awad ibn Lādin")
    assert person_name_phonetic_match(query, result, config).score > 0.3
    assert person_name_phonetic_match(query, result, config).score < 0.9
