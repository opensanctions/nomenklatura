from typing import TYPE_CHECKING
from rigour.names import pick_name
from followthemoney.types import registry

if TYPE_CHECKING:
    from nomenklatura.entity import CompositeEntity


def pick_caption(proxy: "CompositeEntity") -> str:
    for prop_ in proxy.schema.caption:
        prop = proxy.schema.properties[prop_]
        values = [s.value for s in proxy.get_statements(prop)]
        if prop.type == registry.name and len(values) > 1:
            name = pick_name(values)
            if name is not None:
                return name
        for value in values:
            return value
    return proxy.schema.label
