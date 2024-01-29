from typing import TYPE_CHECKING
from rigour.names import pick_name

if TYPE_CHECKING:
    from nomenklatura.entity import CompositeEntity


def pick_caption(proxy: "CompositeEntity") -> str:
    is_thing = proxy.schema.is_a("Thing")
    for prop in proxy.schema.caption:
        values = proxy.get(prop)
        if is_thing and len(values) > 1:
            name = pick_name(values)
            if name is not None:
                return name
        for value in values:
            return value
    return proxy.schema.label
