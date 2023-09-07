from banal import ensure_list, hash_data
from followthemoney import model
from followthemoney.proxy import EntityProxy


def e(schema: str, **kwargs) -> EntityProxy:
    props = {}
    for key, value in kwargs.items():
        if value is not None:
            props[key] = ensure_list(value)
    data = {"schema": schema, "properties": props, "id": hash_data(props)}
    return EntityProxy.from_dict(model, data)
