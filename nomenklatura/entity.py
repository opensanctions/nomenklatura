from hashlib import sha1
from banal import hash_data
from datetime import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
from typing import Generator, Iterable, Tuple, Type, TypeVar
from followthemoney import model
from followthemoney.model import Model
from followthemoney.exc import InvalidData
from followthemoney.types.common import PropertyType
from followthemoney.property import Property
from followthemoney.util import gettext, value_list
from followthemoney.proxy import P
from followthemoney.types import registry
from followthemoney.proxy import EntityProxy

from nomenklatura.dataset import DS
from nomenklatura.publish.names import pick_name
from nomenklatura.statement.statement import Statement

if TYPE_CHECKING:
    from nomenklatura.loader import Loader

CE = TypeVar("CE", bound="CompositeEntity")


class CompositeEntity(EntityProxy):
    """An entity object that can link to a set of datasets that it is sourced from."""

    __slots__ = (
        "schema",
        "id",
        "_caption",
        "target",
        "external",
        "referents",
        "datasets",
        "default_dataset",
        "statement_type",
        "_statements",
    )

    def __init__(
        self,
        model: "Model",
        data: Dict[str, Any],
        cleaned: bool = True,
        default_dataset: str = "default",
    ):
        data = dict(data or {})
        schema = model.get(data.pop("schema", None))
        if schema is None:
            raise InvalidData(gettext("No schema for entity."))
        self.schema = schema

        self._caption: Optional[str] = None
        """A pre-computed label for this entity."""

        self.target: Optional[bool] = data.pop("target", None)
        self.external: Optional[bool] = data.pop("external", None)
        self.referents: Set[str] = set(data.pop("referents", []))
        """The IDs of all entities which are included in this canonical entity."""

        self.datasets: Set[str] = set(data.pop("datasets", []))
        """The set of datasets from which information in this entity is derived."""

        self.default_dataset = default_dataset
        self.id: Optional[str] = data.pop("id", None)
        self._statements: Dict[str, Set[Statement]] = {}

        properties = data.pop("properties", None)
        if isinstance(properties, Mapping):
            for key, value in properties.items():
                self.add(key, value, cleaned=cleaned, quiet=True)

    @property
    def _properties(self) -> Dict[str, List[str]]:  # type: ignore
        return {p: [s.value for s in v] for p, v in self._statements.items()}

    def _iter_stmt(self) -> Generator[Statement, None, None]:
        for stmts in self._statements.values():
            for stmt in stmts:
                if stmt.id is None and stmt.entity_id is not None:
                    stmt.id = stmt.generate_key()
                yield stmt

    def checksum(self) -> str:
        hash = sha1(self.schema.name.encode("utf-8"))
        for stmt in sorted(self._iter_stmt()):
            if stmt.id is not None:
                hash.update(stmt.id.encode("utf-8"))
        return hash.hexdigest()

    @property
    def statements(self) -> Generator[Statement, None, None]:
        if self.id is not None:
            yield Statement(
                canonical_id=self.id,
                entity_id=self.id,
                prop=Statement.BASE,
                prop_type=Statement.BASE,
                schema=self.schema.name,
                value=self.checksum(),
                dataset=self.default_dataset,
            )
        yield from self._iter_stmt()

    @property
    def first_seen(self) -> Optional[datetime]:
        seen = (s.first_seen for s in self._iter_stmt() if s.first_seen is not None)
        return min(seen, default=None)

    @property
    def last_seen(self) -> Optional[datetime]:
        seen = (s.last_seen for s in self._iter_stmt() if s.last_seen is not None)
        return max(seen, default=None)

    @property
    def key_prefix(self) -> Optional[str]:
        return self.default_dataset

    @key_prefix.setter
    def key_prefix(self, dataset: Optional[str]) -> None:
        raise NotImplemented

    def _pick_caption(self) -> str:
        is_thing = self.schema.is_a("Thing")
        for prop in self.schema.caption:
            values = self.get(prop)
            if is_thing and len(values) > 1:
                name = pick_name(values)
                if name is not None:
                    return name
            for value in values:
                return value
        return self.schema.label

    @property
    def caption(self) -> str:
        """The user-facing label to be used for this entity. This checks a list
        of properties defined by the schema (caption) and returns the first
        available value. If no caption is available, return the schema label."""
        if self._caption is None:
            self._caption = self._pick_caption()
        return self._caption

    def add_statement(self, stmt: Statement) -> None:
        # TODO: change target, schema etc. based on data
        if not self.schema.is_a(stmt.schema):
            try:
                self.schema = model.common_schema(self.schema, stmt.schema)
            except InvalidData as exc:
                raise InvalidData(f"{self.id}: {exc}") from exc
        if stmt.target is not None:
            self.target = self.target or stmt.target
        self.datasets.add(stmt.dataset)
        if stmt.entity_id != self.id and stmt.entity_id is not None:
            self.referents.add(stmt.entity_id)
        if stmt.prop != Statement.BASE:
            self._statements.setdefault(stmt.prop, set())
            self._statements[stmt.prop].add(stmt)

    def clean_value(
        self,
        prop: Property,
        value: Optional[str],
        cleaned: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
    ) -> List[str]:
        if value is None:
            return []
        if cleaned:
            return [value]
        value = prop.type.clean_text(value, fuzzy=fuzzy, format=format, proxy=self)
        if value is None:
            return []
        return [value]

    def claim(
        self,
        prop: P,
        value: Optional[str],
        schema: Optional[str] = None,
        dataset: Optional[str] = None,
        seen: Optional[datetime] = None,
        lang: Optional[str] = None,
        original_value: Optional[str] = None,
        cleaned: bool = False,
        quiet: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
    ) -> None:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None:
            return None
        prop = self.schema.properties[prop_name]

        # Don't allow setting the reverse properties:
        if prop.stub:
            if quiet:
                return None
            msg = gettext("Stub property (%s): %s")
            raise InvalidData(msg % (self.schema, prop))

        if lang is not None:
            lang = registry.language.clean_text(lang)

        for clean in self.clean_value(
            prop,
            value,
            cleaned=cleaned,
            fuzzy=fuzzy,
            format=format,
        ):
            if original_value is None and clean != value:
                original_value = value

            stmt = Statement(
                entity_id=self.id,
                prop=prop.name,
                prop_type=prop.type.name,
                schema=schema or self.schema.name,
                value=clean,
                dataset=dataset or self.default_dataset,
                lang=lang,
                original_value=original_value,
                first_seen=seen,
            )
            self.add_statement(stmt)

    def claim_many(
        self,
        prop: P,
        values: Iterable[Optional[str]],
        schema: Optional[str] = None,
        dataset: Optional[str] = None,
        seen: Optional[datetime] = None,
        lang: Optional[str] = None,
        original_value: Optional[str] = None,
        cleaned: bool = False,
        quiet: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
    ) -> None:
        for value in values:
            self.claim(
                prop,
                value,
                schema=schema,
                dataset=dataset,
                seen=seen,
                lang=lang,
                original_value=original_value,
                cleaned=cleaned,
                quiet=quiet,
                fuzzy=fuzzy,
                format=format,
            )

    def get(self, prop: P, quiet: bool = False) -> List[str]:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None or prop_name not in self._statements:
            return []
        return list({s.value for s in self._statements[prop_name]})

    def get_statements(self, prop: P, quiet: bool = False) -> List[Statement]:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None or prop_name not in self._statements:
            return []
        return list(self._statements[prop_name])

    def set(
        self,
        prop: P,
        values: Any,
        cleaned: bool = False,
        quiet: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
    ) -> None:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None:
            return
        self._statements.pop(prop_name, None)
        return self.add(
            prop, values, cleaned=cleaned, quiet=quiet, fuzzy=fuzzy, format=format
        )

    def add(
        self,
        prop: P,
        values: Any,
        cleaned: bool = False,
        quiet: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
        lang: Optional[str] = None,
        original_value: Optional[str] = None,
    ) -> None:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None:
            return None
        prop = self.schema.properties[prop_name]
        for value in value_list(values):
            if not cleaned:
                value = prop.type.clean(value, proxy=self, fuzzy=fuzzy, format=format)
            self.claim(
                prop,
                value,
                quiet=quiet,
                lang=lang,
                original_value=original_value,
                cleaned=True,
            )
        return None

    def unsafe_add(
        self,
        prop: Property,
        value: Optional[str],
        cleaned: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
        lang: Optional[str] = None,
        original_value: Optional[str] = None,
    ) -> None:
        self.claim(
            prop,
            value,
            cleaned=cleaned,
            fuzzy=fuzzy,
            format=format,
            lang=lang,
            original_value=original_value,
        )

    def pop(self, prop: P, quiet: bool = True) -> List[str]:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None or prop_name not in self._statements:
            return []
        return list({s.value for s in self._statements.pop(prop_name, [])})

    def remove(self, prop: P, value: str, quiet: bool = True) -> None:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is not None and prop_name in self._properties:
            stmts = {s for s in self._statements[prop_name] if s.value != value}
            self._statements[prop_name] = stmts

    def itervalues(self) -> Generator[Tuple[Property, str], None, None]:
        for name, statements in self._statements.items():
            prop = self.schema.properties[name]
            for value in set((s.value for s in statements)):
                yield (prop, value)

    def get_type_values(
        self, type_: PropertyType, matchable: bool = False
    ) -> List[str]:
        combined: Set[str] = set()
        for stmt in self.get_type_statements(type_, matchable=matchable):
            combined.add(stmt.value)
        return list(combined)

    def get_type_statements(
        self, type_: PropertyType, matchable: bool = False
    ) -> List[Statement]:
        combined = []
        for prop_name, statements in self._statements.items():
            prop = self.schema.properties[prop_name]
            if matchable and not prop.matchable:
                continue
            if prop.type == type_:
                for statement in statements:
                    combined.append(statement)
        return combined

    @property
    def properties(self) -> Dict[str, List[str]]:
        return {p: list({s.value for s in vs}) for p, vs in self._statements.items()}

    def iterprops(self) -> List[Property]:
        return [self.schema.properties[p] for p in self._statements.keys()]

    def clone(self: CE) -> CE:
        data = {"schema": self.schema.name, "id": self.id}
        cloned = type(self).from_dict(self.schema.model, data)
        for stmt in self._iter_stmt():
            cloned.add_statement(stmt)
        return cloned

    def merge(self: CE, other: "CompositeEntity") -> CE:
        for stmt in other._iter_stmt():
            if self.id is not None:
                stmt.canonical_id = self.id
            self.add_statement(stmt)
        self.referents.update(other.referents)
        self.datasets.update(other.datasets)
        return self

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "caption": self.caption,
            "schema": self.schema.name,
            "properties": self.properties,
            "referents": list(self.referents),
            "datasets": list(self.datasets),
        }
        if self.first_seen is not None:
            data["first_seen"] = self.first_seen
        if self.last_seen is not None:
            data["last_seen"] = self.last_seen
        return data

    def __len__(self) -> int:
        return len(list(self._iter_stmt())) + 1

    def _to_nested_dict(
        self: CE, loader: "Loader[DS, CE]", depth: int, path: List[str]
    ) -> Dict[str, Any]:
        next_depth = depth if self.schema.edge else depth - 1
        next_path = list(path)
        if self.id is not None:
            next_path.append(self.id)
        data = self.to_dict()
        if next_depth < 0:
            return data
        nested: Dict[str, Any] = {}
        for prop, adjacent in loader.get_adjacent(self):
            if adjacent.id in next_path:
                continue
            value = adjacent._to_nested_dict(loader, next_depth, next_path)
            if prop.name not in nested:
                nested[prop.name] = []
            nested[prop.name].append(value)
        data["properties"].update(nested)
        return data

    def to_nested_dict(
        self: CE, loader: "Loader[DS, CE]", depth: int = 1
    ) -> Dict[str, Any]:
        return self._to_nested_dict(loader, depth=depth, path=[])

    @classmethod
    def from_dict(
        cls: Type[CE], model: Model, data: Dict[str, Any], cleaned: bool = True
    ) -> CE:
        return super().from_dict(model, data, cleaned=cleaned)

    @classmethod
    def from_statements(cls: Type[CE], statements: Iterable[Statement]) -> CE:
        obj: Optional[CE] = None
        for stmt in statements:
            if obj is None:
                data = {"schema": stmt.schema, "id": stmt.canonical_id}
                obj = cls(model, data, default_dataset=stmt.dataset)
            obj.add_statement(stmt)
        if obj is None:
            raise ValueError("No statements given!")
        return obj
