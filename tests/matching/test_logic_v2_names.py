from rigour.names import NameTypeTag, NamePartTag, NamePart
from nomenklatura.matching.logic_v2.names.analysis import entity_names
from nomenklatura.matching.logic_v2.names.symbols import Symbol

# from nomenklatura.matching.logic_v2.names.alignment import align_person_name_parts
from nomenklatura.matching.logic_v2.names.util import strict_levenshtein

from .util import e


def test_entity_names_person():
    entity = e("Person", name="Smith, John", firstName="John", lastName="Smith")
    names = entity_names(NameTypeTag.PER, entity)
    assert len(names) == 1
    name = names.pop()
    assert name.form == "smith, john"
    assert name.parts[0].form == "smith"
    assert name.parts[0].tag == NamePartTag.FAMILY
    assert name.parts[1].tag == NamePartTag.GIVEN
    assert len(name.spans) > 0
    for span in name.spans:
        if span.symbol.category == Symbol.Category.PER_ABBR:
            assert span.symbol.id == "j"

    names = {sym.id for sym in name.symbols if sym.category == Symbol.Category.PER_NAME}
    assert 21079662 in names
    # assert False, names


def test_entity_names_company():
    entity = e("Company", name="Westminster Holdings, Ltd.")
    names = entity_names(NameTypeTag.ORG, entity)
    assert len(names) == 1
    name = names.pop()
    assert name.form == "westminster holdings, ltd."
    assert len(name.spans) > 0
    symbols = set()
    for span in name.spans:
        symbols.add(span.symbol)
        if span.symbol.category == Symbol.Category.ORG_TYPE:
            assert span.symbol.id == "LLC"
        if span.symbol.category == Symbol.Category.ORG_SYMBOL:
            assert span.symbol.id == "HOLDING"

    parts = name.non_symbol_parts(symbols)
    assert len(parts) == 1
    assert parts[0].form == "westminster"

    entity = e("Company", name="ABC Gesellschaft mit beschränkter Haftung")
    names = entity_names(NameTypeTag.ORG, entity)
    assert len(names) == 1
    name = names.pop()
    for span in name.spans:
        if span.symbol.category == Symbol.Category.ORG_TYPE:
            assert span.symbol.id == "LLC"
            assert len(span.parts) == 4
    other = e("Company", name="ABC Ltd.")
    other_name = entity_names(NameTypeTag.ORG, other).pop()
    common = name.symbols.intersection(other_name.symbols)
    assert len(common) == 1
    parts = name.non_symbol_parts(common)
    assert len(parts) == 1
    assert parts[0].form == "abc"


# def test_align_person_name_parts():
#     query = [
#         NamePart("john", 0, NamePartTag.GIVEN),
#         NamePart("smith", 1, NamePartTag.FAMILY),
#     ]
#     result = [
#         NamePart("john", 0, NamePartTag.GIVEN),
#         NamePart("smith", 1, NamePartTag.FAMILY),
#     ]
#     aligned = align_person_name_parts(query, result)
#     assert len(aligned) == 2
#     assert aligned[0][0].form == "john"
#     assert aligned[0][1].form == "john"
#     assert aligned[1][0].form == "smith"
#     assert aligned[1][1].form == "smith"
#     query = [
#         NamePart("smith", 0, NamePartTag.FAMILY),
#         NamePart("john", 1, NamePartTag.GIVEN),
#     ]
#     aligned = align_person_name_parts(query, result)
#     assert len(aligned) == 2
#     assert aligned[0][0].form == aligned[0][1].form
#     assert aligned[1][0].form == aligned[1][1].form

#     query = [
#         NamePart("smith", 0, NamePartTag.ANY),
#         NamePart("john", 1, NamePartTag.ANY),
#     ]
#     aligned = align_person_name_parts(query, result)
#     assert len(aligned) == 2
#     assert aligned[0][0].form == aligned[0][1].form
#     assert aligned[1][0].form == aligned[1][1].form

#     query = [
#         NamePart("henry", 1, NamePartTag.GIVEN),
#         NamePart("smith", 0, NamePartTag.ANY),
#         NamePart("john", 1, NamePartTag.GIVEN),
#     ]
#     aligned = align_person_name_parts(query, result)
#     assert len(aligned) == 3
#     assert aligned[0][1] is None
#     assert aligned[1][0].form == aligned[1][1].form
#     assert aligned[2][0].form == aligned[2][1].form

#     query = [
#         NamePart("smith", 0, NamePartTag.GIVEN),
#         NamePart("john", 1, NamePartTag.FAMILY),
#     ]
#     aligned = align_person_name_parts(query, result)
#     assert len(aligned) == 4


def test_strict_levenshtein():
    assert strict_levenshtein("abc", "abc") == 1.0
    assert strict_levenshtein("abc", "ab") == 0.0
    assert strict_levenshtein("hello", "hello") == 1.0
    assert strict_levenshtein("hello", "hullo") > 0.0
    assert strict_levenshtein("hello", "hullo") < 1.0
