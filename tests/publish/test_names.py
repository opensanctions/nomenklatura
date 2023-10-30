from nomenklatura.publish.names import pick_name

PUTIN = [
    "Vladimir Vladimirovich Putin",
    "PUTIN, Vladimir Vladimirovich",
    "Vladimir Vladimirovitj PUTIN",
    "Владимир Владимирович Путин",
    "Vladimir Putin",
    "Vladimir Vladimirovich PUTIN",
    "ПУТІН Володимир Володимирович",
    "ウラジーミル・プーチン",
    "PUTIN Vladimir Vladimirovich",
    "Putin Vladimir Vladimirovich",
    "ПУТИН Владимир Владимирович",
    "Влади́мир Влади́мирович ПУ́ТИН",
    "Путін Володимир Володимирович",
    "Vladimir Vladimirovich POUTINE",
]


def test_pick_putin():
    name = pick_name(PUTIN).lower()
    assert name.endswith("putin"), name


def test_pick_latin():
    names = [
        "Vladimir Vladimirovich Putin",
        "Владимир Владимирович Путин",
        "Владимир Владимирович Путин",
    ]
    name = pick_name(names)
    assert "Putin" in name, name


def test_pick_titlecase():
    names = [
        "Vladimir Vladimirovich Putin",
        "Vladimir Vladimirovich PUTIN",
        "Vladimir Vladimirovich PUTIN",
    ]
    name = pick_name(names)
    assert "Putin" in name, names
