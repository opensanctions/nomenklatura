from nomenklatura.matching.compare.identifiers import orgid_disjoint
from nomenklatura.matching.compare.identifiers import lei_code_match

from .util import e


def test_orgid_disjoint():
    query = e("Company", registrationNumber="77401103")
    result = e("Company", registrationNumber="77401103")
    assert orgid_disjoint(query, result) == 0.0
    result = e("Company", idNumber="77401103")
    assert orgid_disjoint(query, result) == 0.0
    result = e("Company", name="BLA CORP")
    assert orgid_disjoint(query, result) == 0.0
    result = e("Company", registrationNumber="E77401103")
    assert orgid_disjoint(query, result) > 0.0
    assert orgid_disjoint(query, result) < 1.0
    result = e("Company", registrationNumber="83743878")
    assert orgid_disjoint(query, result) == 1.0


def test_lei_match():
    query = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result) == 1.0
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result) == 1.0

    query = e("Company", leiCode="1595VL9OPPQ5THEK2")
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2")
    assert lei_code_match(query, result) == 0.0
