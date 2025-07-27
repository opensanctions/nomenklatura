import yaml
from typing import Dict, List
from followthemoney import Dataset, StatementEntity as Entity
from nomenklatura.matching.logic_v2.model import LogicV2


class Check:
    def __init__(self, schema: str, is_match: bool, query: Entity, candidate: Entity):
        self.schema = schema
        self.is_match = is_match
        self.query = query
        self.candidate = candidate


def make_entity(id: str, schema: str, props: Dict[str, str]) -> Entity:
    """Create a CompositeEntity with the given schema and properties."""
    dataset = Dataset.make({"name": id, "title": id})
    entity = Entity(dataset, {"schema": schema, "id": id})
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


def load_checks() -> List[Check]:
    with open("checks.yml", "r") as fh:
        checks_data = yaml.safe_load(fh)
    checks = checks_data.get("checks", [])
    objects: List[Check] = []
    for check in checks:
        schema = check.get("schema")
        is_match = check.get("match")
        query_ = check.get("query", {})
        query = make_entity("query", schema, query_)
        candidate_ = check.get("candidate", {})
        candidate = make_entity("candidate", schema, candidate_)
        objects.append(Check(schema, is_match, query, candidate))
    return objects


def run_benchmark() -> None:
    """Wrap the matcher function to match the expected signature."""
    checks = load_checks()
    config = LogicV2.default_config()
    func = LogicV2.compare
    print("Running benchmark for: %s" % (func.__name__))
    for i in range(100):
        for check in checks:
            func(check.query, check.candidate, config)


if __name__ == "__main__":
    run_benchmark()
