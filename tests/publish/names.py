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
    assert "Putin" in pick_name(PUTIN), pick_name(PUTIN)


def test_pick_latin():
    name = pick_name(
        [
            "Vladimir Vladimirovich Putin",
            "Владимир Владимирович Путин",
            "Владимир Владимирович Путин",
        ]
    )
    assert "Putin" in name


def test_pick_titlecase():
    name = pick_name(
        [
            "Vladimir Vladimirovich Putin",
            "Vladimir Vladimirovich PUTIN",
            "Vladimir Vladimirovich PUTIN",
        ]
    )
    assert "Putin" in name
