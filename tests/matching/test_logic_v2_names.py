from rigour.names import NameTypeTag, NamePartTag
from nomenklatura.matching.logic_v2.names.analysis import entity_names
from nomenklatura.matching.logic_v2.names.symbols import Symbol

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
        if span.symbol.category == Symbol.Category.INITIAL:
            assert span.symbol.id == "j"

    names = {sym.id for sym in name.symbols if sym.category == Symbol.Category.NAME}
    assert 1158446 in names
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
        if span.symbol.category == Symbol.Category.ORG_CLASS:
            assert span.symbol.id == "LLC"
        if span.symbol.category == Symbol.Category.SYMBOL:
            assert span.symbol.id == "HOLDING"

    entity = e("Company", name="ABC Gesellschaft mit beschränkter Haftung")
    names = entity_names(NameTypeTag.ORG, entity)
    assert len(names) == 1
    name = names.pop()
    for span in name.spans:
        if span.symbol.category == Symbol.Category.ORG_CLASS:
            assert span.symbol.id == "LLC"
            assert len(span.parts) == 1
    other = e("Company", name="ABC Ltd.")
    other_name = entity_names(NameTypeTag.ORG, other).pop()
    common = name.symbols.intersection(other_name.symbols)
    assert len(common) == 1


def test_strict_levenshtein():
    assert strict_levenshtein("abc", "abc") == 1.0
    assert strict_levenshtein("abc", "ab") == 0.0
    assert strict_levenshtein("hello", "hello") == 1.0
    assert strict_levenshtein("hello", "hullo") > 0.0
    assert strict_levenshtein("hello", "hullo") < 1.0
