from nomenklatura.matching.compare.names import name_literal_match
from nomenklatura.matching.compare.names import last_name_mismatch
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.compare.names import person_name_phonetic_match
from nomenklatura.matching.compare.names import weak_alias_match


from .util import e


def test_name_literal_match():
    main = e("Company", name="Siemens AG")
    other = e("Company", name="Siemens AG")
    assert name_literal_match(main, other) == 1.0
    other = e("Company", name="siemens ag")
    assert name_literal_match(main, other) == 1.0
    other = e("Company", name="siemen's ag")
    assert name_literal_match(main, other) == 1.0
    other = e("Company", name="siemen ag")
    assert name_literal_match(main, other) == 0.0
    other = e("Company", name="siemens")
    assert name_literal_match(main, other) == 0.0
    other = e("Company", name="siemens", alias="Siemens AG")
    assert name_literal_match(main, other) == 1.0


def test_last_name_missmatch():
    main = e("Person", lastName="Smith")
    other = e("Person", lastName="Smith")
    assert last_name_mismatch(main, other) == 0.0
    other = e("Person", lastName="Baker")
    assert last_name_mismatch(main, other) == 1.0
    other = e("Person", lastName="Smith-Baker")
    assert last_name_mismatch(main, other) == 0.0


def test_name_fingerprint_levenshtein():
    main = e("Company", name="Siemens AG")
    other = e("Company", name="Siemens Aktiengesellschaft")

    assert name_fingerprint_levenshtein(main, other) == 1.0

    other = e("Company", name="Siemens Aktiongesellschaft")
    assert name_fingerprint_levenshtein(main, other) > 0.0
    assert name_fingerprint_levenshtein(main, other) < 0.5

    other = e("Company", name="Siemens AktG")
    assert name_fingerprint_levenshtein(main, other) > 0.7
    assert name_fingerprint_levenshtein(main, other) < 1.0


def test_arabic_name_similarity():
    name = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    other = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_jaro_winkler(name, other) == 1.0
    other = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_jaro_winkler(name, other) < 1.0
    assert person_name_jaro_winkler(name, other) > 0.7

    other = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_jaro_winkler(name, other) > 0.6
    assert person_name_jaro_winkler(name, other) < 1.0


def test_duplicative_name_similarity():
    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michelle Michaela")
    assert person_name_jaro_winkler(query, result) < 0.7

    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert person_name_jaro_winkler(query, result) > 0.7

    result = e("Person", name="Michelle Obama")
    assert person_name_jaro_winkler(query, result) > 0.3
    assert person_name_jaro_winkler(query, result) < 0.7

    query = e("Person", name="Michaela")
    assert person_name_jaro_winkler(query, result) < 0.5


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) == 0.5

    other = e("Person", name="Hanniball")
    assert person_name_phonetic_match(name, other) == 0.5

    other = e("Person", name="Hannibol")
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) < 0.5
    assert person_name_jaro_winkler(name, other) > 0.2


def test_person_name_phonetic_match():
    query = e("Company", name="Michaela Michelle Micheli")
    result = e("Company", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result) == 0.0

    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert person_name_phonetic_match(query, result) == 1.0

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michelle Michaela")
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_phonetic_match(query, result) > 0.5

    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michell Obama")
    assert person_name_phonetic_match(query, result) > 0.3
    assert person_name_phonetic_match(query, result) < 0.7

    query = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    result = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result) == 1.0
    query = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(query, result) == 1.0

    query = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result) == 1.0

    query = e("Person", name="AL BEN MAHMOUD, Isa Ben Tarif")
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_phonetic_match(query, result) > 0.7


def test_name_alphabets():
    query = e("Person", name="Ротенберг Аркадий")
    result = e("Person", name="Arkadiii Romanovich Rotenberg")
    assert person_name_phonetic_match(query, result) > 0.4
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_jaro_winkler(query, result) > 0.7

    query = e("Person", name="Osama bin Laden")
    result = e("Person", name="Usāma ibn Muhammad ibn Awad ibn Lādin")
    assert person_name_phonetic_match(query, result) > 0.3
    assert person_name_phonetic_match(query, result) < 0.9
    assert person_name_jaro_winkler(query, result) > 0.3
    assert person_name_jaro_winkler(query, result) < 0.9


def test_weak_name_match():
    query = e("Person", name="Abu")
    result = e("Person", weakAlias="ABU.")
    assert weak_alias_match(query, result) == 1.0
    result = e("Person", name="ABU.")
    assert weak_alias_match(query, result) == 0.0
    query = e("Person", weakAlias="Abu")
    result = e("Person", weakAlias="ABU.")
    assert weak_alias_match(query, result) == 1.0
