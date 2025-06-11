from banal import hash_data, ensure_list
from typing import List, TypedDict, Dict, Union
from followthemoney.proxy import EntityProxy
from followthemoney import model
import pytest

from nomenklatura.matching.logic_v2.model import LogicV2
from nomenklatura.matching.types import ScoringConfig

Props = Dict[str, Union[str, List[str]]]
config = ScoringConfig.defaults()


class MatchCase(TypedDict):
    schema: str
    matches: bool
    query: Props
    result: Props


CASES = [
    # People
    {
        "schema": "Person",
        "matches": True,
        "query": {
            "name": "John Doe",
        },
        "result": {
            "name": "John Doe",
        },
    },
    {
        "schema": "Person",
        "matches": True,
        "query": {
            "name": "John Doeburg",
        },
        "result": {
            "name": "John Dowburg",
        },
    },
    {
        "schema": "Person",
        "matches": False,
        "query": {
            "name": "John Doe",
        },
        "result": {
            "name": "John Down",
        },
    },
    {
        "schema": "Person",
        "matches": True,
        "query": {
            "name": "Serei Lavrov",
        },
        "result": {
            "name": "Sergei Lavrov",
        },
    },
    {
        "schema": "Person",
        "matches": True,
        "query": {
            "name": "Serei Lavrov",
        },
        "result": {
            "name": "Сергей Викторович Лавров",
        },
    },
    # Organizations
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "OAO Gazprom",
        },
        "result": {
            "name": "Gazprom JSC",
        },
    },
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "OAO Gazprom",
        },
        "result": {
            "name": "Gasprom JSC",
        },
    },
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "OAO Gazprom",
        },
        "result": {
            "name": "Open Joint Stock Company Gasprom",
        },
    },
    # Vessels
    {
        "schema": "Vessel",
        "matches": True,
        "query": {
            "name": "Snow",
        },
        "result": {
            "name": "SNOW",
        },
    },
    {
        "schema": "Vessel",
        "matches": False,
        "query": {
            "name": "Snow",
        },
        "result": {
            "name": "Snoe",
        },
    },
    {
        "schema": "Vessel",
        "matches": True,
        "query": {
            "name": "Snow Storm 1",
        },
        "result": {
            "name": "Snow Stom 1",
        },
    },
    {
        "schema": "Vessel",
        "matches": False,
        "query": {
            "name": "Snow Storm 1",
        },
        "result": {
            "name": "Snow Storm 2",
        },
    },
]


def _make_entity(schema: str, data: Props) -> EntityProxy:
    """Create a LogicV2 entity from the schema and data."""
    entity_id = hash_data((schema, data))
    props = {k: ensure_list(v) for k, v in data.items()}
    entity = {"schema": schema, "id": entity_id, "properties": props}
    return EntityProxy.from_dict(model, entity, cleaned=False)


@pytest.mark.parametrize("case", CASES)
def test_match_cases(case: MatchCase) -> None:
    query = _make_entity(case["schema"], case["query"])
    result = _make_entity(case["schema"], case["result"])
    res = LogicV2().compare(query, result, config)
    if case["matches"]:
        assert res.score > 0.7, (
            f"Expected match for {case['query']!r} and {case['result']!r}",
            res,
        )
    else:
        assert res.score < 0.7, (
            f"Expected no match for {case['query']!r} and {case['result']!r}",
            res,
        )
