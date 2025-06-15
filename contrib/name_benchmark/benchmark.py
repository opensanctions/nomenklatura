from typing import Callable, Dict, List
from rich.console import Console
from rich.table import Table
import yaml

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity as Entity


class Check:
    def __init__(self, schema: str, is_match: bool, query: Entity, candidate: Entity):
        self.schema = schema
        self.is_match = is_match
        self.query = query
        self.candidate = candidate


class Result:
    def __init__(self, check: Check, score: float, threshold: float):
        self.check = check
        self.score = score
        self.threshold = threshold
        self.true_score = 1.0 if check.is_match else 0.0
        self.is_match = score >= threshold
        self.is_correct = self.is_match == check.is_match
        self.loss = abs(self.true_score - score)


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


def stub_compare(query: Entity, candidate: Entity) -> float:
    """Stub compare function."""
    return 0.9


def run_benchmark(
    func: Callable[[Entity, Entity], float], threshold: float = 0.8
) -> None:
    """Run the benchmark."""
    checks = load_checks()
    results = []
    print("Running benchmark for: %s (threshold: %.2f)" % (func.__name__, threshold))
    for check in checks:
        score = func(check.query, check.candidate)
        result = Result(check, score, threshold)
        results.append(result)

    console = Console()

    failures = Table(title="Failed results")
    failures.add_column("Query", justify="left")
    failures.add_column("Candidate", justify="left")
    failures.add_column("Correct", justify="right")
    failures.add_column("Result", justify="right")
    failures.add_column("Score", justify="right")
    failures.add_column("Loss", justify="right")

    for result in results:
        if result.is_correct:
            continue
        failures.add_row(
            result.check.query.first("name"),
            result.check.candidate.first("name"),
            str(result.check.is_match),
            str(result.is_match),
            "%.2f" % result.score,
            "%.2f" % result.loss,
        )
    if len(failures.rows) > 0:
        console.print(failures)

    table = Table(title="Confusion Matrix by Schema")
    table.add_column("Schema", justify="left")
    table.add_column("Checks", justify="right")
    table.add_column("Correct", justify="right", style="green")
    table.add_column("%", justify="right", style="green")
    table.add_column("False positives", justify="right", style="yellow")
    table.add_column("False negatives", justify="right", style="red")
    table.add_column("avg. Loss", justify="right")

    schemata = set(check.schema for check in checks)
    for schema in sorted(schemata):
        schema_results = [result for result in results if result.check.schema == schema]
        correct = sum(result.is_correct for result in schema_results)
        false_positives = sum(
            1 for result in schema_results if result.is_match and not result.is_correct
        )
        false_negatives = sum(
            1
            for result in schema_results
            if not result.is_match and not result.is_correct
        )
        avg_loss = sum(result.loss for result in schema_results) / len(schema_results)
        pct_correct = correct / len(schema_results) * 100.0
        table.add_row(
            schema,
            str(len(schema_results)),
            str(correct),
            "%.1f" % pct_correct,
            str(false_positives),
            str(false_negatives),
            "%.3f" % avg_loss,
        )

    total_correct = sum(result.is_correct for result in results)
    total_loss = sum(result.loss for result in results)
    total_count = len(results)
    pct_correct = total_correct / total_count * 100.0
    total_false_positives = sum(
        1 for result in results if result.is_match and not result.is_correct
    )
    total_false_negatives = sum(
        1 for result in results if not result.is_match and not result.is_correct
    )
    table.add_row(
        "TOTAL",
        str(total_count),
        str(total_correct),
        "%.1f" % pct_correct,
        str(total_false_positives),
        str(total_false_negatives),
        "%.3f" % (total_loss / total_count),
    )
    console.print(table)


def wrap_matcher(query: Entity, candidate: Entity) -> float:
    """Wrap the matcher function to match the expected signature."""
    from nomenklatura.matching.logic_v2.names import name_match
    from nomenklatura.matching.logic_v2.model import LogicV2

    config = LogicV2.default_config()
    return name_match(query, candidate, config).score


if __name__ == "__main__":
    run_benchmark(wrap_matcher, threshold=0.7)
