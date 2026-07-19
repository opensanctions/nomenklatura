from banal import hash_data, ensure_list
from typing import List, TypedDict, Dict, Union
from followthemoney import EntityProxy
import pytest

from nomenklatura.matching.logic_v2.model import LogicV2

Props = Dict[str, Union[str, List[str]]]
config = LogicV2.default_config()


class PairCase(TypedDict):
    schema: str
    better: Props
    worse: Props
    result: Props


CASES: List[PairCase] = [
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin"},
        "worse": {"name": "Waldimyr Pytin"},
        "result": {"name": "Vladimir Putin"},
    },
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin"},
        "worse": {"name": "Vladimir Putin", "birthDate": "1957-10-07"},
        "result": {"name": "Vladimir Putin", "birthDate": "1952-10-07"},
    },
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin", "birthDate": "1952-10-07"},
        "worse": {"name": "Vladimir Putin", "birthDate": "1957-10-07"},
        "result": {"name": "Vladimir Putin", "birthDate": "1952-10-07"},
    },
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin", "birthDate": "1952-10-07"},
        "worse": {"name": "Vladimir Putin", "birthDate": "1952-01-07"},
        "result": {"name": "Vladimir Putin", "birthDate": "1952-10-07"},
    },
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin"},
        "worse": {"name": "Vladimir Putin", "nationality": "fr"},
        "result": {"name": "Vladimir Putin", "nationality": "ru"},
    },
    {
        "schema": "Person",
        "better": {"name": "Vladimir Putin", "nationality": "ru"},
        "worse": {"name": "Vladimir Putin", "nationality": "fr"},
        "result": {"name": "Vladimir Putin", "nationality": "ru"},
    },
    {
        "schema": "Company",
        "better": {"swiftBic": "TRCBUS33"},
        "worse": {"name": "TRCA Bank"},
        "result": {"name": "TRC Bank", "swiftBic": "TRCBUS33"},
    },
    {
        "schema": "Company",
        "better": {"name": "Street Ban GmbH"},
        "worse": {"name": "Street Ban LLC"},
        "result": {"name": "Street Bank GmbH"},
    },
    {
        "schema": "Company",
        "better": {"name": "Westminister Management Limited"},
        "worse": {"name": "Westminister Management Limited", "jurisdiction": "fr"},
        "result": {"name": "Westminister Management Limited", "jurisdiction": "gb"},
    },
    {
        "schema": "Company",
        "better": {"name": "Westminister Management Limited", "jurisdiction": "gb"},
        "worse": {"name": "Westminister Management Limited", "jurisdiction": "fr"},
        "result": {"name": "Westminister Management Limited", "jurisdiction": "gb"},
    },
    {
        "schema": "Company",
        "better": {"name": "Westminister менеджмент Limited"},
        "worse": {"name": "Westminister менемент Limited"},
        "result": {"name": "Westminister Management Limited"},
    },
    {
        "schema": "Vessel",
        "better": {"name": "Sea Pony 1"},
        "worse": {"name": "Sea Poni 1"},
        "result": {"name": "Sea Pony 1"},
    },
    {
        "schema": "Vessel",
        "better": {"name": "Sea Pony 1"},
        "worse": {"name": "Sea Pony 2"},
        "result": {"name": "Sea Pony 1"},
    },
]


def _make_entity(schema: str, data: Props) -> EntityProxy:
    """Create a LogicV2 entity from the schema and data."""
    entity_id = hash_data((schema, data))
    props = {k: ensure_list(v) for k, v in data.items()}
    entity = {"schema": schema, "id": entity_id, "properties": props}
    return EntityProxy.from_dict(entity, cleaned=False)


@pytest.mark.parametrize("case", CASES)
def test_match_cases(case: PairCase) -> None:
    better = _make_entity(case["schema"], case["better"])
    worse = _make_entity(case["schema"], case["worse"])
    result = _make_entity(case["schema"], case["result"])
    better_res = LogicV2().compare(better, result, config)
    worse_res = LogicV2().compare(worse, result, config)
    msg = f"Expected {better_res.score} to be greater than {worse_res.score}"
    assert worse_res.score < better_res.score, msg
