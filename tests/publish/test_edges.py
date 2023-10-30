from typing import Dict, Any
from followthemoney import model
from nomenklatura.entity import CompositeEntity
from nomenklatura.publish.edges import simplify_undirected


def _e(schema: str, **props: Dict[str, Any]) -> CompositeEntity:
    data = {"schema": schema, "properties": props, "id": "test"}
    return CompositeEntity.from_dict(model, data)


def test_family_simplified():
    ent = _e("Family", person=["Q7747", "ofac-2332"], relative=["Q7747", "ofac-2332"])
    assert len(ent.get("person")) == 2, ent.to_dict()
    simp = simplify_undirected(ent)
    assert simp.schema.name == "Family"
    assert simp.get("person") == ["Q7747"], simp.to_dict()
    assert simp.get("relative") == ["ofac-2332"], simp.to_dict()

    ent = _e("Family", person=["ofac-2332"], relative=["Q7747"])
    simp = simplify_undirected(ent)
    assert simp.get("person") == ["ofac-2332"], simp.to_dict()
    assert simp.get("relative") == ["Q7747"], simp.to_dict()


def test_payment_simplified():
    ent = _e(
        "Payment",
        payer=["Q7747", "ofac-2332"],
        beneficiary=["Q7747", "ofac-2332"],
    )
    assert len(ent.get("payer")) == 2, ent.to_dict()
    simp = simplify_undirected(ent)
    assert simp.schema.name == "Payment"
    assert sorted(simp.get("payer")) == sorted(["Q7747", "ofac-2332"])
