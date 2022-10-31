from typing import Any, Dict, List
from followthemoney import model
from followthemoney.types import registry

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

    sp.claim("notes", "Ich bin eine banane!", lang="deu")
    claim = sp.get_statements("notes")[0]
    assert claim.lang == "deu", claim

    sp.claim("country", "Germany")
    claim = sp.get_statements("country")[0]
    assert claim.value == "de", claim
    assert claim.original_value == "Germany", claim

    pre_len = len(sp)
    sp.claim_many("country", ["de", "it", "fr"])
    assert pre_len + 2 == len(sp), sp._statements["country"]

    stmts = list(sp.statements)
    assert len(stmts) == len(sp), stmts
    assert sorted(stmts)[0].prop == Statement.BASE
