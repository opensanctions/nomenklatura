from followthemoney import model

from nomenklatura.publish.dates import simplify_dates
from nomenklatura.entity import CompositeEntity

ENTITY = {
    "id": "demo",
    "schema": "Person",
    "properties": {
        "birthDate": ["1972", "1972-04", "1972-04-12"],
        "createdAt": ["2023-01-01", "2023-03-03"],
    },
}


def test_simplify_dates():
    entity = CompositeEntity.from_dict(model, ENTITY)
    assert len(entity.get("birthDate")) == 3
    assert len(entity.get("createdAt")) == 2
    simple = simplify_dates(entity)
    assert simple.get("birthDate") == ["1972-04-12"]
    assert simple.get("createdAt") == ["2023-01-01"]
