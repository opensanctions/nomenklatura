import orjson

from nomenklatura.statement import Statement
from nomenklatura.util import pack_prop, unpack_prop


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
    schema, _, prop = unpack_prop(prop_id)
    return Statement(
        id=id,
        entity_id=entity_id,
        prop=prop,
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
