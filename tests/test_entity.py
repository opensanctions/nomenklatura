from nomenklatura.loader import FileLoader


DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"


def test_nested_entity(dloader: FileLoader):
    entity = dloader.get_entity(DAIMLER)
    assert entity is not None, entity
    data = entity.to_nested_dict(dloader)
    properties = data["properties"]
    addresses = properties["addressEntity"]
    assert len(addresses) == 2, addresses
    assert "paymentBeneficiary" not in properties
    assert len(properties["paymentPayer"]) == 8, len(properties["paymentPayer"])
    payment = properties["paymentPayer"][0]
    assert payment["schema"] == "Payment"
    payprops = payment["properties"]
    assert isinstance(payprops["payer"][0], str), payment
    assert isinstance(payprops["beneficiary"][0], dict), payment
