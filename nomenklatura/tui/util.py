from typing import Generator
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.entity import CE

TYPE_ORDER = {
    registry.name: -6,
    registry.identifier: -5,
    registry.date: -4,
    registry.country: -3,
    registry.string: -1,
    registry.text: 3,
}


def comparison_props(left: CE, right: CE) -> Generator[Property, None, None]:
    """Return an ordered list of properties to be shown in a comparison of
    the two given entities."""
    props = set(left.iterprops())
    props.update(right.iterprops())
    weights = {p.name: TYPE_ORDER.get(p.type, 0) for p in props}
    for prop in props:
        for schema in (left.schema, right.schema):
            if prop.name in schema.featured:
                weights[prop.name] -= 10

    key = lambda p: (weights[p.name], p.label)
    for prop in sorted(props, key=key):
        if prop.hidden:
            continue
        if prop.type.matchable and not prop.matchable:
            continue
        # if prop.type == registry.entity:
        #     continue
        yield prop
