import hashlib
from datetime import datetime
from typing import Dict, Generator, Optional, Type, TypeVar, TypedDict

from nomenklatura.entity import CE
from nomenklatura.statements.util import (
    bool_text,
    datetime_iso,
    iso_datetime,
    text_bool,
)

S = TypeVar("S", bound="Statement")

#
# Candidates for columns:
# * language/locale
# * original_value
# * transformer
# * source_url
# * confidence (wikidata rank)
#
# Get rid of:
# * target
# * last_seen/first_seen -> timestamp
#


class StatementDict(TypedDict):
    id: str
    entity_id: str
    canonical_id: str
    prop: str
    prop_type: str
    schema: str
    value: str
    dataset: str
    target: Optional[bool]
    external: Optional[bool]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]


class Statement(object):
    """A single statement about a property relevant to an entity.

    For example, this could be useddocker to say: "In dataset A, entity X has the
    property `name` set to 'John Smith'. I first observed this at K, and last
    saw it at L."

    Null property values are not supported. This might need to change if we
    want to support making property-less entities.
    """

    BASE = "id"

    __slots__ = [
        "id",
        "entity_id",
        "canonical_id",
        "prop",
        "prop_type",
        "schema",
        "value",
        "dataset",
        "target",
        "external",
        "first_seen",
        "last_seen",
    ]

    def __init__(
        self,
        entity_id: str,
        prop: str,
        prop_type: str,
        schema: str,
        value: str,
        dataset: str,
        first_seen: Optional[datetime] = None,
        target: Optional[bool] = False,
        external: Optional[bool] = False,
        id: Optional[str] = None,
        canonical_id: Optional[str] = None,
        last_seen: Optional[datetime] = None,
    ):
        self.entity_id = entity_id
        self.canonical_id = canonical_id or entity_id
        self.prop = prop
        self.prop_type = prop_type
        self.schema = schema
        self.value = value
        self.dataset = dataset
        self.first_seen = first_seen
        self.last_seen = last_seen or first_seen
        self.target = target
        self.external = external
        if id is None:
            id = self.make_key(dataset, entity_id, prop, value, external)
        self.id = id

    def to_row(self) -> Dict[str, Optional[str]]:
        return {
            "canonical_id": self.canonical_id,
            "entity_id": self.entity_id,
            "prop": self.prop,
            "prop_type": self.prop_type,
            "schema": self.schema,
            "value": self.value,
            "dataset": self.dataset,
            "first_seen": datetime_iso(self.first_seen),
            "last_seen": datetime_iso(self.last_seen),
            "target": bool_text(self.target),
            "external": bool_text(self.external),
            "id": self.id,
        }

    def to_dict(self) -> StatementDict:
        return {
            "canonical_id": self.canonical_id,
            "entity_id": self.entity_id,
            "prop": self.prop,
            "prop_type": self.prop_type,
            "schema": self.schema,
            "value": self.value,
            "dataset": self.dataset,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "target": self.target,
            "external": self.external,
            "id": self.id,
        }

    @classmethod
    def make_key(
        cls,
        dataset: str,
        entity_id: str,
        prop: str,
        value: str,
        external: Optional[bool],
    ) -> str:
        """Hash the key properties of a statement record to make a unique ID."""
        key = f"{dataset}.{entity_id}.{prop}.{value}"
        if external:
            # We consider the external flag in key composition to avoid race conditions where
            # a certain entity might be emitted as external while it is already linked in to
            # the graph via another route.
            key = f"{key}.ext"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls: Type[S], data: StatementDict) -> S:
        return cls(
            entity_id=data["entity_id"],
            prop=data["prop"],
            prop_type=data["prop_type"],
            schema=data["schema"],
            value=data["value"],
            dataset=data["dataset"],
            first_seen=data.get("first_seen", None),
            target=data.get("target"),
            external=data.get("external"),
            id=data.get("id", None),
            canonical_id=data.get("canonical_id", None),
            last_seen=data.get("last_seen", None),
        )

    @classmethod
    def from_row(cls: Type[S], data: Dict[str, str]) -> S:
        return cls(
            entity_id=data["entity_id"],
            prop=data["prop"],
            prop_type=data["prop_type"],
            schema=data["schema"],
            value=data["value"],
            dataset=data["dataset"],
            first_seen=iso_datetime(data.get("first_seen", None)),
            target=text_bool(data.get("target")),
            external=text_bool(data.get("external")),
            id=data.get("id", None),
            canonical_id=data.get("canonical_id", None),
            last_seen=iso_datetime(data.get("last_seen", None)),
        )

    @classmethod
    def from_entity(
        cls: Type[S],
        entity: CE,
        dataset: str,
        first_seen: Optional[datetime] = None,
        last_seen: Optional[datetime] = None,
        target: Optional[bool] = None,
        external: Optional[bool] = None,
    ) -> Generator[S, None, None]:
        yield cls(
            entity_id=entity.id,
            prop=cls.BASE,
            prop_type=cls.BASE,
            schema=entity.schema.name,
            value=entity.id,
            dataset=dataset,
            target=target,
            external=external,
            first_seen=first_seen,
            last_seen=last_seen,
        )
        for prop, value in entity.itervalues():
            yield cls(
                entity_id=entity.id,
                prop=prop.name,
                prop_type=prop.type.name,
                schema=entity.schema.name,
                value=value,
                dataset=dataset,
                target=target,
                external=external,
                first_seen=first_seen,
                last_seen=last_seen,
            )
