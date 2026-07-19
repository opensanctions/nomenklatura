from nomenklatura.matching.logic_v2.names.match import name_match
from nomenklatura.matching.logic_v2.model import LogicV2

from ...factory import e

config = LogicV2.default_config()


def test_name_match():
    query = e("Person", name="John Smith")
    result = e("Person", name="Smith, John")
    res = name_match(query, result, config)
    assert res.score == 1.0
    assert res.query == "John Smith"
    assert res.candidate == "Smith, John"


# def test_specific():
#     left = e("Company", name="N.A.B.C Company")
#     right = e("Company", name="A.B.C. Company")
#     config = LogicV2.default_config()
#     assert not name_match(left, right, config)
