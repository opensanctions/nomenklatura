from nomenklatura.matching.logic_v2.identifiers import lei_code_match
from nomenklatura.matching.logic_v2.identifiers import bic_code_match
from nomenklatura.matching.logic_v2.identifiers import isin_security_match
from nomenklatura.matching.logic_v2.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()

def test_query_candidate_set():
    """Test that the query and candidate values are set correctly on the result."""
    # Internally, the logic is the same for all identifiers, but we try
    # different identifier types across the test cases anyway.
    
    # Both query and candidate have the same identifier in correct format
    query = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    res = lei_code_match(query, result, config)
    assert res.query == "1595VL9OPPQ5THEK2X30"
    assert res.candidate == "1595VL9OPPQ5THEK2X30"
    
    # Non-match: different identifier values
    query = e("Company", swiftBic="GENODEM1")
    result = e("Company", swiftBic="GENODEM2")
    res = bic_code_match(query, result, config)
    assert res.query is None
    assert res.candidate is None
    
    # Out-of-format match: query has identifier in generic property, candidate has it in format-specific property
    query = e("Security", registrationNumber="US4581401001")
    result = e("Security", isin="US4581401001")
    res = isin_security_match(query, result, config)
    assert res.query == "US4581401001"
    assert res.candidate == "US4581401001"
    
    # Out-of-format match: query has identifier in format-specific property, candidate has it in generic property
    query = e("Vessel", imoNumber="IMO9929429")
    result = e("Vessel", registrationNumber="IMO9929429")
    res = vessel_imo_mmsi_match(query, result, config)
    assert res.query == "IMO9929429"
    assert res.candidate == "IMO9929429"





def test_lei_match():
    query = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0

    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0

    query = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    result = e("Company", leiCode="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 1.0
    # neither entity has the correct format prop:
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2X30")
    assert lei_code_match(query, result, config).score == 0.0

    query = e("Company", leiCode="1595VL9OPPQ5THEK2")
    result = e("Company", registrationNumber="1595VL9OPPQ5THEK2")
    assert lei_code_match(query, result, config).score == 0.0


def test_bic_match():
    query = e("Company", swiftBic="GENODEM1")
    result = e("Company", swiftBic="GENODEM1")
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


def test_imo_match():
    query = e("Vessel", imoNumber="IMO9929429", country="lr")
    result = e("Vessel", imoNumber="IMO9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", imoNumber="IMO9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", registrationNumber="IMO9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 1.0

    result = e("Vessel", imoNumber="9929429")
    assert vessel_imo_mmsi_match(query, result, config).score == 0.0
