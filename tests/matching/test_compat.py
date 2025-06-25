from nomenklatura.matching.compat import fingerprint_name


def test_fingerprint_name():
    assert fingerprint_name("OAO Gazprom") == fingerprint_name(
        "Open Joint Stock Company Gazprom"
    )
