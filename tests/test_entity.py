import pytest
from datetime import datetime
from typing import Any, Dict, List
from followthemoney import model
from followthemoney.types import registry
from followthemoney.exc import InvalidData

from nomenklatura.store import SimpleMemoryStore
from nomenklatura.entity import CompositeEntity
from nomenklatura.dataset import Dataset
from nomenklatura.statement.statement import Statement

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
EXAMPLE = {
    "id": "bla",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}


def test_nested_entity(dstore: SimpleMemoryStore):
    view = dstore.default_view()
    entity = view.get_entity(DAIMLER)
    assert entity is not None, entity
    data = entity.to_nested_dict(view)
    properties = data["properties"]
    addresses = properties["addressEntity"]
    assert len(addresses) == 2, addresses
    assert "paymentBeneficiary" not in properties
    assert len(properties["paymentPayer"]) == 8, len(properties["paymentPayer"])
    payment = properties["paymentPayer"][0]
    assert payment["schema"] == "Payment"
    payprops = payment["properties"]
    assert isinstance(payprops["payer"][0], str), payment
    assert isinstance(payprops["beneficiary"][0], dict), payment


def test_donations_entities(donations_json: List[Dict[str, Any]]):
    for data in donations_json:
        sp = CompositeEntity.from_dict(model, data)
        assert sp.schema is not None
        assert sp.id is not None
        assert len(sp) > 0


def test_example_entity():
    dx = Dataset.make({"name": "test", "title": "Test"})
    sp = CompositeEntity.from_dict(model, EXAMPLE, default_dataset=dx)
    assert len(sp) == 3
    assert sp.checksum() == "836baf194d59a68c4092e208df30134800c732cc"
    assert sp.caption == "John Doe"
    assert "John Doe", sp.get_type_values(registry.name)
    sp.add("country", "us")
    assert len(sp) == 4
    assert sp.checksum() == "c3aec8e1fcd86bc55171917db7c993d6f3ad5fe0"
    sp.add("country", {"gb"})
    assert len(sp) == 5
    sp.add("country", ("gb", "us"))
    assert len(sp) == 5
    sp.add("country", ["gb", "us"])
    assert len(sp) == 5
    sp.set("country", "gb")
    assert len(sp) == 4
    data = sp.to_dict()
    assert data["id"] == sp.id, data
    so = sp.clone()
    assert so.id == sp.id
    assert so.default_dataset == sp.default_dataset
    assert so.checksum() == sp.checksum()

    sx = CompositeEntity.from_statements(sp.statements)
    assert sx.id == sp.id
    assert len(sx) == len(sp)

    sp.add("notes", "Ich bin eine banane!", lang="deu")
    claim = sp.get_statements("notes")[0]
    assert claim.lang == "deu", claim

    sp.add("banana", "Ich bin eine banane!", lang="deu", quiet=True)

    assert len(sp.get_statements("notes")) == 1
    sp.add("notes", None, lang="deu", quiet=True)
    assert len(sp.get_statements("notes")) == 1

    sp.add("alias", "Banana Boy")
    assert len(sp.get_statements("alias")) == 1

    sp.add("nationality", "Germany")
    claim = sp.get_statements("nationality")[0]
    assert claim.value == "de", claim
    assert claim.prop == "nationality", claim
    assert claim.prop_type == "country", claim
    assert claim.original_value == "Germany", claim

    for prop, val in sp.itervalues():
        if prop.name == "nationality":
            assert val == "de"

    pre_len = len(sp)
    sp.add("nationality", "de")
    sp.add("nationality", "it")
    sp.add("nationality", "fr")
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
        schema="LegalEntity",
        value="Jane Doe",
        dataset="test",
    )
    sp = CompositeEntity.from_statements([smt])
    assert sp.id == "blubb"
    assert sp.schema.name == "LegalEntity"
    assert "test" in sp.datasets
    assert sp.first_seen is None

    dt = datetime.utcnow()
    smt2 = Statement(
        entity_id="gnaa",
        prop="birthDate",
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
