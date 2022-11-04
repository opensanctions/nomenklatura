import pytest
from datetime import datetime
from typing import Any, Dict, List
from followthemoney import model
from followthemoney.types import registry
from followthemoney.exc import InvalidData

from nomenklatura.statement.entity import StatementProxy
from nomenklatura.statement.model import Statement

EXAMPLE = {
    "id": "bla",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}


def test_donations_entities(donations_json: List[Dict[str, Any]]):
    for data in donations_json:
        sp = StatementProxy.from_dict(model, data)
        assert sp.schema is not None
        assert sp.id is not None
        assert len(sp) > 0


def test_example_entity():
    sp = StatementProxy.from_dict(model, EXAMPLE)
    assert len(sp) == 3
    assert sp.caption == "John Doe"
    assert "John Doe", sp.get_type_values(registry.name)
    sp.add("country", "us")
    assert len(sp) == 4
    sp.set("country", "gb")
    assert len(sp) == 4
    data = sp.to_dict()
    assert data["id"] == sp.id, data
    so = sp.clone()
    assert so.id == sp.id

    sx = StatementProxy.from_statements(sp.statements)
    assert sx.id == sp.id
    assert len(sx) == len(sp)

    sp.claim("notes", "Ich bin eine banane!", lang="deu")
    claim = sp.get_statements("notes")[0]
    assert claim.lang == "deu", claim

    sp.claim("banana", "Ich bin eine banane!", lang="deu", quiet=True)

    assert len(sp.get_statements("notes")) == 1
    sp.claim("notes", None, lang="deu", quiet=True)
    assert len(sp.get_statements("notes")) == 1

    sp.unsafe_add("alias", "Banana Boy")
    assert len(sp.get_statements("alias")) == 1

    sp.claim("nationality", "Germany")
    claim = sp.get_statements("nationality")[0]
    assert claim.value == "de", claim
    assert claim.prop == "nationality", claim
    assert claim.prop_type == "country", claim
    assert claim.original_value == "Germany", claim

    for prop, val in sp.itervalues():
        if prop.name == "nationality":
            assert val == "de"

    pre_len = len(sp)
    sp.claim_many("nationality", ["de", "it", "fr"])
    assert pre_len + 2 == len(sp), sp._statements["country"]
    assert len(sp.get_type_values(registry.country)) == 4

    sp.remove("nationality", "it")
    assert len(sp.get("nationality")) == 2
    sp.pop("nationality")
    assert len(sp.get("nationality")) == 0

    stmts = list(sp.statements)
    assert len(stmts) == len(sp), stmts
    assert sorted(stmts)[0].prop == Statement.BASE


def test_other_entity():
    smt = Statement(
        entity_id="blubb",
        prop="name",
        prop_type="name",
        schema="LegalEntity",
        value="Jane Doe",
        dataset="test",
    )
    sp = StatementProxy.from_statements([smt])
    assert sp.id == "blubb"
    assert sp.schema.name == "LegalEntity"
    assert "test" in sp.datasets
    assert sp.first_seen is None

    dt = datetime.utcnow()
    smt2 = Statement(
        entity_id="gnaa",
        prop="birthDate",
        prop_type="date",
        schema="Person",
        value="1979",
        dataset="source",
        first_seen=dt,
    )
    sp.add_statement(smt2)
    assert sp.id == "blubb"
    assert sp.schema.name == "Person"
    assert sp.first_seen == dt

    with pytest.raises(InvalidData):
        smt2 = Statement(
            entity_id="gnaa",
            prop="incorporationDate",
            prop_type="date",
            schema="Company",
            value="1979",
            dataset="source",
        )
        sp.add_statement(smt2)

    with pytest.raises(InvalidData):
        sp.add("identification", "abc")
    sp.add("identification", "abc", quiet=True)

    sp.add("alias", "Harry", lang="deu")
    aliases = sp.get_statements("alias")
    assert aliases[0].lang == "deu", aliases
