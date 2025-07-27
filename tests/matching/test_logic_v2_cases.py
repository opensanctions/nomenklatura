from banal import hash_data, ensure_list
from typing import List, TypedDict, Dict, Union
from followthemoney import EntityProxy
import pytest

from nomenklatura.matching.logic_v2.model import LogicV2

Props = Dict[str, Union[str, List[str]]]
config = LogicV2.default_config()


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
        "matches": False,
        "query": {
            "name": "John Doe",
        },
        "result": {
            "name": "Juan Doe",
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
            "name": "Serej Lavrov",
        },
        "result": {
            "name": "Сергей Викторович Лавров",
        },
    },
    {
        "schema": "Person",
        "matches": True,
        "query": {
            "name": "Ramimakhlouf",
        },
        "result": {
            "name": "Rami Makhlouf",
        },
    },
    {
        "schema": "Person",
        "matches": False,
        "query": {
            "name": "A Nazarbayev",
        },
        "result": {
            "name": "Nursultan Naza",
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
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "Gazprom Neft JSC",
        },
        "result": {
            "name": "Gazprom Neft OAO",
        },
    },
    {
        "schema": "Company",
        "matches": False,
        "query": {
            "name": "LXC Aviation",
        },
        "result": {
            "name": "LAU Aviation",
        },
    },
    {
        "schema": "Company",
        "matches": False,
        "query": {
            "name": "LXC Aviatio",
        },
        "result": {
            "name": "LAU Aviation",
        },
    },
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "LXC Aviation",
        },
        "result": {
            "name": "L.X.C Aviation",
        },
    },
    {
        "schema": "Company",
        "matches": False,
        "query": {
            "name": "L.X.C. Aviation",
        },
        "result": {
            "name": "LAU Aviation",
        },
    },
    {
        "schema": "Company",
        "matches": False,
        "query": {
            "name": "OJSC TACTICAL KITTENS CORPORATION",
        },
        "result": {
            "name": "TACTICAL MISSILES CORPORATION JOINT STOCK COMPANY",
        },
    },
    {
        "schema": "Company",
        "matches": True,
        "query": {
            "name": "FABERLIC EUROPE",
        },
        "result": {
            "name": "FABERLIC EUROPE Sp. z o.o.",
        },
    },
    {
        "schema": "Organization",
        "matches": True,
        "query": {
            "name": "Brigade Fourty-four",
        },
        "result": {
            "name": "Brigade 44",
        },
    },
    {
        "schema": "Organization",
        "matches": True,
        "query": {
            "swiftBic": "COBADEFFXXX",
        },
        "result": {
            "registrationNumber": "COBADEFF",
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
    {
        "schema": "Vessel",
        "matches": True,
        "query": {
            "name": "Snow Storm 1",
            "imoNumber": "9929429",
        },
        "result": {
            "name": "Snow Storm 2",
            "imoNumber": "IMO9929429",
        },
    },
]


def _make_entity(schema: str, data: Props) -> EntityProxy:
    """Create a LogicV2 entity from the schema and data."""
    entity_id = hash_data((schema, data))
    props = {k: ensure_list(v) for k, v in data.items()}
    entity = {"schema": schema, "id": entity_id, "properties": props}
    return EntityProxy.from_dict(entity, cleaned=False)


@pytest.mark.parametrize("case", CASES)
def test_match_cases(case: MatchCase) -> None:
    query = _make_entity(case["schema"], case["query"])
    result = _make_entity(case["schema"], case["result"])
    res = LogicV2().compare(query, result, config)
    if case["matches"]:
        assert res.score > 0.7, res
    else:
        assert res.score < 0.7, res
