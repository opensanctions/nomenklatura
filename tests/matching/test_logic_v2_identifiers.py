from nomenklatura.matching.logic_v2.identifiers import lei_code_match
from nomenklatura.matching.logic_v2.identifiers import bic_code_match
from nomenklatura.matching.logic_v2.identifiers import isin_security_match
from nomenklatura.matching.logic_v2.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_lei_match():
    query = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0

    query = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score > 0
    assert lei_code_match(query, result, config).score < 1.0

    query = e("Company", leiCode="1595VL9OPPQ5THEK2")
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2")
    assert lei_code_match(query, result, config).score == 0.0


def test_bic_match():
    query = e("Company", swiftBic="GENODEM1GLS")
    result = e("Company", swiftBic="GENODEM1GLS")
    assert bic_code_match(query, result, config).score == 1.0
    result = e("Company", swiftBic="GENODEM1")
    assert bic_code_match(query, result, config).score == 1.0
    result = e("Company", swiftBic="GENODEM2")
    assert bic_code_match(query, result, config).score == 0.0


def test_isin_match():
    query = e("Security", isin="US4581401001")
    result = e("Security", isin="US4581401001")
    assert isin_security_match(query, result, config).score == 1.0
    result = e("Security", isin="US4581401002")
    assert isin_security_match(query, result, config).score == 0.0
    query = e("Security", isin="4581401002")
    result = e("Security", isin="4581401002")
    assert isin_security_match(query, result, config).score == 0.0


def test_imo_match():
    query = e("Vessel", imoNumber="IMO 9929429", country="lr")
    result = e("Vessel", imoNumber="IMO 9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", imoNumber="9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", registrationNumber="9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", imoNumber="992942")
    assert vessel_imo_mmsi_match(query, result, config).score == 0.0
