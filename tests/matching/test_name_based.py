from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import NameMatcher, NameQualifiedMatcher
from nomenklatura.matching.name_based.names import jaro_name_parts
from nomenklatura.matching.name_based.names import soundex_name_parts

from .util import e


def _make_named(*names):
    data = {"id": "test", "schema": "Person", "properties": {"name": names}}
    return Entity.from_dict(model, data)


def test_heuristic_scoring():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameMatcher.compare(a, b).score == 1.0
    b = _make_named("Vladimir Pudin")
    assert NameMatcher.compare(a, b).score < 1.0
    assert NameMatcher.compare(a, b).score >= 0.95


def test_heuristic_qualified_country():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameQualifiedMatcher.compare(a, b).score == 1.0
    a.add("country", "pa")
    b.add("country", "ru")
    assert NameQualifiedMatcher.compare(a, b).score == 0.9


def test_heuristic_qualified_dob():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameQualifiedMatcher.compare(a, b).score == 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1952-05-01")
    assert NameQualifiedMatcher.compare(a, b).score == 0.85
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1962-05-01")
    assert NameQualifiedMatcher.compare(a, b).score == 0.75


def test_heuristic_qualified_corp():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    assert NameQualifiedMatcher.compare(a, b).score == 1.0
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "748745")
    assert NameQualifiedMatcher.compare(a, b).score == 0.9
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "E137332")
    assert NameQualifiedMatcher.compare(a, b).score > 0.9


def test_heuristic_overrides():
    overrides = {
        jaro_name_parts.__name__: 0.0,
        soundex_name_parts.__name__: 0.0,
    }
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    result = NameQualifiedMatcher.compare(a, b, overrides)
    assert result.score == 0.0
    overrides = {
        jaro_name_parts.__name__: 1.0,
        soundex_name_parts.__name__: 0.0,
    }
    result = NameQualifiedMatcher.compare(a, b, overrides)
    assert result.score == 1.0
    assert len(result.features) == 1


def test_soundex_name_comparison():
    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert soundex_name_parts(query, result) == 1.0

    result = e("Person", name="Michelle Michi")
    assert soundex_name_parts(query, result) == 1.0

    result = e("Person", name="Donald Duck")
    assert soundex_name_parts(query, result) == 0.0


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert soundex_name_parts(name, other) == 1.0

    other = e("Person", name="Hanniball")
    assert soundex_name_parts(name, other) == 1.0

    other = e("Person", name="Hannibol")
    assert soundex_name_parts(name, other) == 1.0
