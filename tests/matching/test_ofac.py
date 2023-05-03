from followthemoney import model

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching import OFAC249Matcher, OFAC249QualifiedMatcher


def _make_named(*names):
    data = {"id": "test", "schema": "Person", "properties": {"name": names}}
    return Entity.from_dict(model, data)


def test_ofac_scoring():
    a = _make_named("Vladimir Putin")
    b = _make_named("Vladimir Putin")
    assert OFAC249Matcher.compare(a, b)["score"] == 1.0
    b = _make_named("Vladimir Pudin")
    assert OFAC249Matcher.compare(a, b)["score"] == 0.95


def test_ofac_qualified_country():
    a = _make_named("Vladimir Putin")
    b = _make_named("Vladimir Putin")
    assert OFAC249QualifiedMatcher.compare(a, b)["score"] == 1.0
    a.add("country", "pa")
    b.add("country", "ru")
    assert OFAC249QualifiedMatcher.compare(a, b)["score"] == 0.9


def test_ofac_qualified_dob():
    a = _make_named("Vladimir Putin")
    b = _make_named("Vladimir Putin")
    assert OFAC249QualifiedMatcher.compare(a, b)["score"] == 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1952-05-01")
    assert OFAC249QualifiedMatcher.compare(a, b)["score"] == 0.9
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1962-05-01")
    assert OFAC249QualifiedMatcher.compare(a, b)["score"] == 0.8
