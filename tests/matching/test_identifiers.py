from nomenklatura.matching.compare.identifiers import crypto_wallet_address
from nomenklatura.matching.types import ScoringConfig

from .util import e

config = ScoringConfig.defaults()


def test_crypto_wallet():
    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result, config).score == 1.0

    query = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")
    result = e("CryptoWallet", publicKey="bc1qxy2kgdygjrsqtzq2n0yrf2484p83kkfjhx0wlh")
    assert crypto_wallet_address(query, result, config).score == 0.0
