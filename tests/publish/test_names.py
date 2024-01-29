from followthemoney import model

from nomenklatura.publish.names import pick_caption
from nomenklatura.entity import CompositeEntity

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
    entity = CompositeEntity.from_dict(model, {"schema": "Person", 'id': 'putin'})
    assert pick_caption(entity) == "Person"

    data = {"schema": "Person", 'id': 'putin', 'properties': {'name': PUTIN}}
    entity = CompositeEntity.from_dict(model, data)
    assert pick_caption(entity).lower().endswith("putin"), entity.caption
