from nomenklatura.matching.compare.identifiers import orgid_disjoint
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


def test_crypto_wallet():
    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result) == 1.0

    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2484p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result) == 0.0
