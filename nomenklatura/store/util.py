import orjson
from hashlib import sha1
from functools import cache
from typing import Tuple
from followthemoney import model

from nomenklatura.statement import Statement

QNAME_PREFIX = 5


def pack_prop(schema: str, prop: str) -> str:
    return f"{schema}:{prop}"


@cache
def unpack_prop(id: str) -> Tuple[str, str, str]:
    schema, prop = id.split(":", 1)
    if prop == Statement.BASE:
        return schema, Statement.BASE, Statement.BASE
    schema_obj = model.get(schema)
    if schema_obj is None:
        raise TypeError("Schema not found: %s" % schema)
    prop_obj = schema_obj.get(prop)
    if prop_obj is None:
        raise TypeError("Property not found: %s" % prop)
    return schema, prop_obj.type.name, prop


def pack_statement(stmt: Statement) -> bytes:
    values = (
        stmt.id,
        stmt.entity_id,
        stmt.dataset,
        pack_prop(stmt.schema, stmt.prop),
        stmt.value,
        stmt.lang,
        stmt.original_value,
        stmt.first_seen,
        stmt.last_seen,
        stmt.target,
    )
    return orjson.dumps(values)


def unpack_statement(data: bytes, canonical_id: str, external: bool) -> Statement:
    (
        id,
        entity_id,
        dataset,
        prop_id,
        value,
        lang,
        original_value,
        first_seen,
        last_seen,
        target,
    ) = orjson.loads(data)
    schema, prop_type, prop = unpack_prop(prop_id)
    return Statement(
        id=id,
        entity_id=entity_id,
        prop=prop,
        prop_type=prop_type,
        schema=schema,
        value=value,
        lang=lang,
        dataset=dataset,
        original_value=original_value,
        first_seen=first_seen,
        last_seen=last_seen,
        target=target,
        canonical_id=canonical_id,
        external=external,
    )
