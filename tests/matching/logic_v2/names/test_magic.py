from collections.abc import Sequence

from rigour.names import Name, NamePart, NamePartTag, Symbol

from nomenklatura.matching.logic_v2.names.analysis import entity_names_consolidated
from nomenklatura.matching.logic_v2.names.magic import (
    EXTRAS_WEIGHTS,
    extra_match_weights,
    weight_extra_match,
)

from ...factory import e


def _scan_weight(parts: Sequence[NamePart], name: Name) -> float:
    """Reference: fold the extras weight by scanning every span of the name."""
    if len(parts) == 1 and parts[0].tag == NamePartTag.STOP:
        return 0.5
    sparts = tuple(parts)
    weight = 1.0
    for span in name.spans:
        if span.symbol.category == Symbol.Category.NUMERIC:
            part = span.parts[0]
            if len(span.parts) == 1 and not part.numeric and len(part.comparable) < 2:
                continue
        if span.parts == sparts:
            weight = weight * EXTRAS_WEIGHTS.get(span.symbol.category, 1.0)
    return weight


def _name(schema: str, text: str, is_query: bool = False) -> Name:
    names = entity_names_consolidated(e(schema, name=text), is_query=is_query)
    assert len(names) == 1
    return next(iter(names))


def test_extra_match_weights_org_class():
    name = _name("Company", "Siemens AG")
    weights = extra_match_weights(name)
    by_form = {parts[0].form: w for parts, w in weights.items() if len(parts) == 1}
    assert by_form["ag"] == EXTRAS_WEIGHTS[Symbol.Category.ORG_CLASS]
    assert "siemens" not in by_form


def test_extra_match_weights_skips_identity_spans():
    name = _name("Person", "Vladimir Vladimirovich Putin")
    assert all(s.symbol.category == Symbol.Category.NAME for s in name.spans)
    assert extra_match_weights(name) == {}


def test_extra_match_weights_folds_repeated_spans():
    name = Name("Foo Bar", tag=Name("x").tag)
    part = name.parts[0]
    name.apply_part(part, Symbol(Symbol.Category.ORG_CLASS, "a"))
    name.apply_part(part, Symbol(Symbol.Category.LOCATION, "b"))
    weights = extra_match_weights(name)
    expected = (
        EXTRAS_WEIGHTS[Symbol.Category.ORG_CLASS]
        * EXTRAS_WEIGHTS[Symbol.Category.LOCATION]
    )
    assert weights[(part,)] == expected


def test_extra_match_weights_skips_degenerate_numeric():
    name = Name("X Corp")
    part = name.parts[0]
    assert not part.numeric and len(part.comparable) < 2
    name.apply_part(part, Symbol(Symbol.Category.NUMERIC, "10"))
    assert (part,) not in extra_match_weights(name)
    other = Name("12 Corp")
    other.apply_part(other.parts[0], Symbol(Symbol.Category.NUMERIC, "12"))
    assert (
        extra_match_weights(other)[(other.parts[0],)]
        == EXTRAS_WEIGHTS[Symbol.Category.NUMERIC]
    )


def test_weight_extra_match_lookup():
    name = _name("Company", "Bank of Siemens AG")
    weights = extra_match_weights(name)
    by_form = {p.form: p for p in name.parts}
    assert weight_extra_match((by_form["of"],), weights) == 0.5
    assert weight_extra_match((by_form["siemens"],), weights) == 1.0
    assert (
        weight_extra_match((by_form["ag"],), weights)
        == EXTRAS_WEIGHTS[Symbol.Category.ORG_CLASS]
    )


def test_weight_extra_match_matches_span_scan():
    cases = [
        ("Company", "Open Joint Stock Company Stroygazmontazh International 12"),
        ("Company", "Siemens Russia GmbH"),
        ("Company", "PE Fund 1"),
        ("Person", "Arkady Romanovich Rotenberg"),
        ("Person", "Dr. J. R. Smith"),
        ("Organization", "The Bank of New York Mellon Corporation"),
        ("Company", "Deutsche Bank AG Filiale Hamburg"),
    ]
    for schema, text in cases:
        for is_query in (False, True):
            name = _name(schema, text, is_query=is_query)
            weights = extra_match_weights(name)
            for part in name.parts:
                assert weight_extra_match((part,), weights) == _scan_weight(
                    (part,), name
                ), (text, part.form)
