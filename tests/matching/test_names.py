from nomenklatura.matching.compare.names import name_literal_match
from nomenklatura.matching.compare.names import last_name_mismatch
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.compare.names import person_name_phonetic_match
from nomenklatura.matching.compare.names import weak_alias_match
from nomenklatura.matching.compare.names import name_metaphone_match, name_soundex_match


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
    query = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    result = e("Person", name="Shaikh Isa Bin Tarif Al Bin Ali")
    assert person_name_jaro_winkler(query, result) == 1.0
    query = e("Person", name="Isa Bin Tarif Al Bin Ali")
    assert person_name_jaro_winkler(query, result) == 1.0

    query = e("Person", name="AL BEN ALI, Isa Ben Tarif")
    assert person_name_jaro_winkler(query, result) > 0.6
    assert person_name_jaro_winkler(query, result) < 1.0


def test_duplicative_name_similarity():
    query = e("Person", name="Michaela Michelle Micheli")
    result = e("Person", name="Michelle Michaela")
    assert person_name_jaro_winkler(query, result) == 0.0

    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert person_name_jaro_winkler(query, result) == 1.0

    query = e("Person", name="Michele Michaela")
    assert person_name_jaro_winkler(query, result) > 0.7
    assert person_name_jaro_winkler(query, result) < 1.0

    query = e("Person", name="Michele Nichaela")
    assert person_name_jaro_winkler(query, result) > 0.7
    assert person_name_jaro_winkler(query, result) < 1.0

    query = e("Person", name="Michele Nychaela")
    assert person_name_jaro_winkler(query, result) > 0.7
    assert person_name_jaro_winkler(query, result) < 1.0

    query = e("Person", name="Michele Mugaloo")
    assert person_name_jaro_winkler(query, result) < 0.7
    query = e("Person", name="Michaela")
    assert person_name_jaro_winkler(query, result) > 0.7

    result = e("Person", name="Michelle Obama")
    assert person_name_jaro_winkler(query, result) == 0.0


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) == 1.0

    other = e("Person", name="Hanniball")
    assert person_name_phonetic_match(name, other) == 0.5

    other = e("Person", name="Hannibol")
    assert person_name_phonetic_match(name, other) == 0.5
    assert person_name_jaro_winkler(name, other) > 0.8
    assert person_name_jaro_winkler(name, other) < 1.0


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


def test_person_name_jaro_winkler():
    query = e("Person", name="Jan Daniel Bothma")
    result = e("Person", name="RAZAFIMAHATRATRA Jean Daniel Christian")
    assert person_name_jaro_winkler(query, result) < 0.7

    query = e("Person", name="Friedrich Lindenberg")
    false_positives = [
        "Lars Friedrich Lindemann",
        "Wolfgang Friedrich Ischinger",
        "Gerhard Friedrich Karl Westdickenberg",
        "Klaus-Peter Friedrich Walter Schulze",
    ]
    for fp in false_positives:
        result = e("Person", name=fp)
        assert person_name_jaro_winkler(query, result) < 0.8

    true_positives = [
        "Fridrich Lindenberg",
        "Fredrich Lindenberg",
        "Friedrich Lindenburg",
        "Friedrich Lyndenburg",
    ]
    for fp in true_positives:
        result = e("Person", name=fp)
        assert person_name_jaro_winkler(query, result) > 0.88

    query = e("Person", name="Frederik Richter")
    false_positives = [
        "Frederick Matthias Benjamin Bolte",
        "Matthi Bolte-Richter",
        "Frank Richter",
    ]
    for fp in false_positives:
        result = e("Person", name=fp)
        assert person_name_jaro_winkler(query, result) < 0.8

    query = e("Person", name="Barack Obama")
    result = e("Person", name="George Hussein Onyango Obama")
    assert person_name_jaro_winkler(query, result) < 0.7

    result = e("Person", name="Barak Obama")
    assert person_name_jaro_winkler(query, result) > 0.9

    result = e("Person", name="Barackk Obama")
    assert person_name_jaro_winkler(query, result) > 0.9

    result = e("Person", name="Michelle Obama")
    assert person_name_jaro_winkler(query, result) < 0.7

    query = e("Person", name="Michelle Obama")
    result = e("Person", name="Marie-Thérèse Obama")
    assert person_name_jaro_winkler(query, result) < 0.7

    result = e("Person", name="Michel Obama")
    assert person_name_jaro_winkler(query, result) > 0.9

    query = e("Person", name="Pol Pot")
    result = e("Person", name="Paul Murphy")
    assert person_name_jaro_winkler(query, result) < 0.7
    result = e("Person", name="Paul Mitchell")
    assert person_name_jaro_winkler(query, result) < 0.7
    result = e("Person", name="Pot Pouv")
    assert person_name_jaro_winkler(query, result) < 1.0
    assert person_name_jaro_winkler(query, result) > 0.7

    query = e("Person", name="Thomas Lindemann")
    false_positives = [
        "Jeremy Thomas England",
        "Niranjan Thomas Alva",
        "Iain Thomas Rankin",
    ]
    for fp in false_positives:
        result = e("Person", name=fp)
        assert person_name_jaro_winkler(query, result) < 0.7

    result = e("Person", name="Thomas A. Lind")
    assert person_name_jaro_winkler(query, result) < 0.8


def test_name_alphabets():
    query = e("Person", name="Ротенберг Аркадий")
    result = e("Person", name="Arkadiii Romanovich Rotenberg")
    assert person_name_phonetic_match(query, result) > 0.4
    assert person_name_phonetic_match(query, result) < 1.0
    assert person_name_jaro_winkler(query, result) > 0.7

    query = e("Person", name="Osama bin Laden")
    result = e("Person", name="Usāma bin Muhammad ibn Awad ibn Lādin")
    assert person_name_phonetic_match(query, result) > 0.3
    assert person_name_phonetic_match(query, result) < 0.9
    assert person_name_jaro_winkler(query, result) > 0.5
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
