from nomenklatura.matching.compare.names import name_literal_match
from nomenklatura.matching.compare.names import last_name_mismatch
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.compare.names import soundex_name_parts
from nomenklatura.matching.compare.names import person_name_phonetic_match


from .util import e


def test_name_literal_match():
    main = e("Company", name="Siemens AG")
    other = e("Company", name="Siemens AG")
    assert name_literal_match(main, other) == 1.0
    other = e("Company", name="siemens ag")
    assert name_literal_match(main, other) == 1.0
    other = e("Company", name="siemen's ag")
    assert name_literal_match(main, other) == 0.0
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
    name = e("Person", name="Michaela Michelle Micheli")
    other = e("Person", name="Michelle Michaela")
    assert person_name_jaro_winkler(name, other) > 0.7

    other = e("Person", name="Michelle Obama")
    assert person_name_jaro_winkler(name, other) > 0.3
    assert person_name_jaro_winkler(name, other) < 0.7

    other = e("Person", name="Michaela")
    assert person_name_jaro_winkler(name, other) == 0.5


def test_soundex_name_comparison():
    name = e("Person", name="Michaela Michelle Micheli")
    other = e("Person", name="Michelle Michaela")
    assert soundex_name_parts(name, other) < 1.0
    assert soundex_name_parts(name, other) > 0.7

    other = e("Person", name="Michelle Michi")
    assert soundex_name_parts(name, other) > 0.3
    assert soundex_name_parts(name, other) < 0.7

    other = e("Person", name="Donald Duck")
    assert soundex_name_parts(name, other) == 0.0


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert soundex_name_parts(name, other) == 0.5
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) == 0.5

    other = e("Person", name="Hanniball")
    assert soundex_name_parts(name, other) == 0.5
    assert person_name_phonetic_match(name, other) == 0.5

    other = e("Person", name="Hannibol")
    assert soundex_name_parts(name, other) == 0.5
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) < 0.5
    assert person_name_jaro_winkler(name, other) > 0.2


def test_person_name_phonetic_match():
    name = e("Company", name="Michaela Michelle Micheli")
    other = e("Company", name="Michelle Michaela")
    assert person_name_phonetic_match(name, other) == 0.0

    name = e("Person", name="Michaela Michelle Micheli")
    other = e("Person", name="Michelle Michaela")
    assert person_name_phonetic_match(name, other) < 1.0
    assert person_name_phonetic_match(name, other) > 0.7

    name = e("Person", name="Michaela Michelle Micheli")
    other = e("Person", name="Michell Obama")
    assert person_name_phonetic_match(name, other) > 0.3
    assert person_name_phonetic_match(name, other) < 0.7

    name = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    other = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(name, other) == 1.0
    other = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_phonetic_match(name, other) < 1.0
    assert person_name_phonetic_match(name, other) > 0.9

    other = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_phonetic_match(name, other) < 1.0
    assert person_name_phonetic_match(name, other) > 0.9


def test_name_alphabets():
    name = e("Person", name="Arkadiii Romanovich Rotenberg")
    other = e("Person", name="Ротенберг Аркадий")
    assert person_name_phonetic_match(name, other) > 0
    assert person_name_phonetic_match(name, other) < 1.0
    assert person_name_jaro_winkler(name, other) > 0.7

    name = e("Person", name="Usāma ibn Muhammad ibn Awad ibn Lādin")
    other = e("Person", name="Osama bin Laden")
    assert person_name_phonetic_match(name, other) > 0.1
    assert person_name_jaro_winkler(name, other) > 0.3
