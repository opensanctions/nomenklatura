from followthemoney import ValueEntity as Entity
from nomenklatura.matching.name_based.model import NameMatcher, NameQualifiedMatcher
from nomenklatura.matching.name_based.model import OFACMatcher
from nomenklatura.matching.name_based.names import jaro_name_parts
from nomenklatura.matching.name_based.names import soundex_name_parts
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

config = ScoringConfig.defaults()


def _make_named(*names):
    data = {"id": "test", "schema": "Person", "properties": {"name": names}}
    return Entity.from_dict(data)


def test_heuristic_scoring():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameMatcher.compare(a, b, config).score == 1.0
    b = _make_named("Vladimir Pudin")
    assert NameMatcher.compare(a, b, config).score < 1.0
    assert NameMatcher.compare(a, b, config).score >= 0.95


def test_heuristic_qualified_country():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameQualifiedMatcher.compare(a, b, config).score == 1.0
    a.add("country", "pa")
    b.add("country", "ru")
    assert NameQualifiedMatcher.compare(a, b, config).score == 0.9


def test_heuristic_qualified_dob():
    a = e("Person", name="Vladimir Putin")
    b = e("Person", name="Vladimir Putin")
    assert NameQualifiedMatcher.compare(a, b, config).score == 1.0
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1952-05-01")
    assert NameQualifiedMatcher.compare(a, b, config).score == 0.85
    a.set("birthDate", "1952-02-10")
    b.set("birthDate", "1962-05-01")
    assert NameQualifiedMatcher.compare(a, b, config).score == 0.75


def test_heuristic_qualified_corp():
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    assert NameQualifiedMatcher.compare(a, b, config).score == 1.0
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "748745")
    assert NameQualifiedMatcher.compare(a, b, config).score == 0.9
    a.set("registrationNumber", "137332")
    b.set("registrationNumber", "E137332")
    assert NameQualifiedMatcher.compare(a, b, config).score > 0.9


def test_heuristic_overrides():
    overrides = {
        jaro_name_parts.__name__: 0.0,
        soundex_name_parts.__name__: 0.0,
    }
    config = ScoringConfig(weights=overrides, config={})
    a = e("Company", name="CRYSTALORD LTD")
    b = e("Company", name="CRYSTALORD LTD")
    result = NameQualifiedMatcher.compare(a, b, config)
    assert result.score == 0.0
    assert len(result.explanations) == 0
    overrides = {
        jaro_name_parts.__name__: 1.0,
        soundex_name_parts.__name__: 0.0,
    }
    config = ScoringConfig(weights=overrides, config={})
    result = NameQualifiedMatcher.compare(a, b, config)
    assert result.score == 1.0
    assert len(result.explanations) == 4


def test_ofac_matcher_compare():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    result = OFACMatcher.compare(a, b, config)
    assert result.score == 1.0
    assert (
        result.explanations["ofac_name_score"].detail
        == "whole-string=0.00, per-token=1.00"
    )

    b = e("Person", name="HASWANI, George")
    result = OFACMatcher.compare(a, b, config)
    assert result.score < 0.8
    # First-letter gate rejects V vs H; per-token mean is low because no
    # query token has a strong candidate match.
    assert (
        result.explanations["ofac_name_score"].detail
        == "whole-string=0.00, per-token=0.26"
    )


def test_ofac_matcher_qualifier_penalties():
    """Country / DOB mismatches reduce the name score (departs from
    FAQ 251). The reduction is surfaced as a separate entry in
    `result.explanations` (the firing qualifier feature) rather than
    folded into the name-feature detail."""
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    result = OFACMatcher.compare(a, b, config)
    assert result.score == 1.0
    # No qualifier fires; name-feature detail is unchanged.
    assert "country_mismatch" not in result.explanations
    assert (
        result.explanations["ofac_name_score"].detail
        == "whole-string=0.00, per-token=1.00"
    )
    a.add("country", "ru")
    b.add("country", "us")
    result = OFACMatcher.compare(a, b, config)
    # Score drops by the country_mismatch weight (-0.1); the qualifier
    # is what explains the reduction.
    assert result.score == 0.9
    assert (
        result.explanations["ofac_name_score"].detail
        == "whole-string=0.00, per-token=1.00"
    )
    assert (
        result.explanations["country_mismatch"].detail
        == "Different countries: ['ru'] / ['us']"
    )
