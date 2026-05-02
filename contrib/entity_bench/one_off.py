from typing import Dict
from uuid import uuid4

from followthemoney import ValueEntity as Entity, model
from nomenklatura.matching.types import FtResult
from nomenklatura.matching.logic_v2.names.match import name_match
from nomenklatura.matching.logic_v2.model import LogicV2


def make_entity(schema: str, props: Dict[str, str]) -> Entity:
    """Create a CompositeEntity with the given schema and properties."""
    schema_obj = model.get(schema)
    assert schema_obj is not None, f"Schema not found: {schema}"
    entity_id = uuid4().hex
    entity = Entity(schema_obj, {"id": entity_id})
    for prop, value in props.items():
        entity.add(prop, value)
    if not len(entity.names):
        parts = [
            entity.first("firstName"),
            entity.first("secondName"),
            entity.first("middleName"),
            entity.first("fatherName"),
            entity.first("motherName"),
            entity.first("lastName"),
        ]
        name = " ".join(filter(None, parts))
        entity.add("name", name)
    return entity


def run_one_off(query: Entity, candidate: Entity) -> FtResult:
    """Wrap the matcher function to match the expected signature."""
    config = LogicV2.default_config()
    result = name_match(query, candidate, config)
    print(f"Score: {result.score:.2f}")
    if result.detail:
        print(f"Detail: {result.detail}")
    return result


if __name__ == "__main__":
    query = make_entity("Organization", {"name": "PLA China"})
    candidate = make_entity("Organization", {"name": "People's Liberation Army"})

    run_one_off(query, candidate)
