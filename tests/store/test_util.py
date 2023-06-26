from followthemoney import model

from nomenklatura.store.util import pack_prop, pack_statement
from nomenklatura.store.util import unpack_prop, unpack_statement


def test_packing_unique():
    seen = set()
    for prop in model.properties:
        packed = pack_prop(prop.schema.name, prop.name)
        assert packed not in seen, (packed, prop)
        seen.add(packed)
