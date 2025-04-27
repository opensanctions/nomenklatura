from rigour.names import NameTypeTag, NamePartTag
from nomenklatura.matching.logic_v2.names import entity_names
from nomenklatura.matching.logic_v2.names.symbols import Symbol

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
