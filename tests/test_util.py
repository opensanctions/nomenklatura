from followthemoney import model

from nomenklatura.util import pack_prop, unpack_prop


def test_packing_unique():
    seen = set()
    for prop in model.properties:
        packed = pack_prop(prop.schema.name, prop.name)
        assert packed not in seen, (packed, prop)
        seen.add(packed)
        schema, _, prop_name = unpack_prop(packed)
        assert prop.schema.name == schema, (prop, schema)
        assert prop.name == prop_name, (prop, prop_name)
