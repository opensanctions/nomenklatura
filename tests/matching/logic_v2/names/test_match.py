from nomenklatura.matching.logic_v2.model import LogicV2
from nomenklatura.matching.logic_v2.names.analysis import entity_names
from nomenklatura.matching.logic_v2.names.magic import (
    extra_match_weights,
    weight_extra_match,
)
from nomenklatura.matching.logic_v2.names.match import name_match

from ...factory import e

config = LogicV2.default_config()


def test_name_match():
    query = e("Person", name="John Smith")
    result = e("Person", name="Smith, John")
    res = name_match(query, result, config)
    assert res.score == 1.0
    assert res.query == "John Smith"
    assert res.candidate == "Smith, John"


def test_name_match_reversed_part_tags():
    # https://github.com/opensanctions/nomenklatura/issues/247 — a query with
    # firstName/lastName swapped produces the same comparable string as a
    # "Family, Given"-form alias on the result. That must not short-circuit
    # to a 1.0 literal match: the part tags contradict each other.
    result = e(
        "Person",
        name=["Vladimir Putin", "PUTIN, Vladimir"],
        firstName="Vladimir",
        lastName="Putin",
    )
    reversed_query = e(
        "Person",
        name="putin vladimir",
        firstName="putin",
        lastName="vladimir",
    )
    res = name_match(reversed_query, result, config)
    assert res.score < 0.7, res

    correct_query = e(
        "Person",
        name="vladimir putin",
        firstName="vladimir",
        lastName="putin",
    )
    res = name_match(correct_query, result, config)
    assert res.score == 1.0, res

    # An untagged result name in reversed order stays a literal match: its
    # UNSET parts haven't committed to a role, so nothing contradicts.
    untagged_result = e("Person", name="putin vladimir")
    res = name_match(reversed_query, untagged_result, config)
    assert res.score == 1.0, res


# def test_specific():
#     left = e("Company", name="N.A.B.C Company")
#     right = e("Company", name="A.B.C. Company")
#     config = LogicV2.default_config()
#     assert not name_match(left, right, config)


def _part(entity, form):
    for name in entity_names(entity):
        for part in name.parts:
            if part.form == form:
                return name, part
    raise AssertionError(form)


def test_stopword_extra_weight_uses_part_tag():
    # Diacritic stopwords carry the STOP tag from analysis even though the
    # wordlist lookup on the raw form misses them.
    name, part = _part(e("Organization", name="Verein für Deutsche Sprache"), "für")
    assert weight_extra_match((part,), extra_match_weights(name)) == 0.5
    name, part = _part(e("Company", name="Bank of America"), "of")
    assert weight_extra_match((part,), extra_match_weights(name)) == 0.5
    # A stopword-shaped token claimed by a property tag is not filler.
    entity = e("Person", name="Charles de Gaulle", lastName="de Gaulle")
    name, part = _part(entity, "de")
    assert weight_extra_match((part,), extra_match_weights(name)) == 1.0
