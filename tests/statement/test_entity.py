from typing import Any, Dict, List
from followthemoney import model
from followthemoney.types import registry

from nomenklatura.statement.entity import StatementProxy

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
    assert len(sp) == 2
    assert sp.caption == "John Doe"
    assert "John Doe", sp.get_type_values(registry.name)
    sp.add("country", "us")
    assert len(sp) == 3
    sp.set("country", "gb")
    assert len(sp) == 3
    data = sp.to_dict()
    assert data["id"] == sp.id, data
    so = sp.clone()
    assert so.id == sp.id
