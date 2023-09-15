from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import NameMatcher, NameQualifiedMatcher

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
