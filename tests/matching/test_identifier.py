from nomenklatura.matching.compare.identifiers import orgid_disjoint
from nomenklatura.matching.compare.identifiers import lei_code_match
from nomenklatura.matching.compare.identifiers import bic_code_match
from nomenklatura.matching.compare.identifiers import isin_security_match
from nomenklatura.matching.compare.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.compare.identifiers import crypto_wallet_address

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


def test_bic_match():
    query = e("Company", swiftBic="GENODEM1GLS")
    result = e("Company", swiftBic="GENODEM1GLS")
    assert bic_code_match(query, result) == 1.0
    result = e("Company", swiftBic="GENODEM1")
    assert bic_code_match(query, result) == 1.0
    result = e("Company", swiftBic="GENODEM2")
    assert bic_code_match(query, result) == 0.0


def test_isin_match():
    query = e("Security", isin="US4581401001")
    result = e("Security", isin="US4581401001")
    assert isin_security_match(query, result) == 1.0
    result = e("Security", isin="US4581401002")
    assert isin_security_match(query, result) == 0.0
    query = e("Security", isin="4581401002")
    result = e("Security", isin="4581401002")
    assert isin_security_match(query, result) == 0.0


def test_imo_match():
    query = e("Vessel", imoNumber="IMO 9929429", country="lr")
    result = e("Vessel", imoNumber="IMO 9929429")
    assert vessel_imo_mmsi_match(query, result) == 1.0

    result = e("Vessel", imoNumber="9929429")
    assert vessel_imo_mmsi_match(query, result) == 1.0

    result = e("Vessel", imoNumber="992942")
    assert vessel_imo_mmsi_match(query, result) == 0.0


def test_crypto_wallet():
    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result) == 1.0

    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2484p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result) == 0.0
