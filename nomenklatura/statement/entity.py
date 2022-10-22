from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Set,
    Tuple,
)
from banal import ensure_dict
from followthemoney import model
from followthemoney.exc import InvalidData
from followthemoney.types.common import PropertyType
from followthemoney.property import Property
from followthemoney.util import gettext
from followthemoney.proxy import P
from followthemoney.model import Model

from nomenklatura.entity import CompositeEntity
from nomenklatura.statement.model import Statement


class StatementProxy(CompositeEntity):
    __slots__ = [
        "schema",
        "id",
        "key_prefix",
        "context",
        "statement_type",
        "_statements",
    ]

    def __init__(
        self,
        model: "Model",
        data: Dict[str, Any],
        key_prefix: Optional[str] = None,
        cleaned: bool = True,
        default_dataset: str = "default",
    ):
        data = dict(data or {})
        schema = model.get(data.pop("schema", None))
        if schema is None:
            raise InvalidData(gettext("No schema for entity."))
        self.schema = schema
        self.target: Optional[bool] = data.pop("target", None)
        self.referents: Set[str] = set()
        self.datasets: Set[str] = set()
        self.default_dataset = default_dataset
        self.key_prefix = key_prefix
        self.id = data.pop("id", None)
        self._statements: Dict[str, Set[Statement]] = {}

        properties = data.pop("properties", {})
        if properties is not None:
            properties = ensure_dict(properties)
            for key, value in properties.items():
                if key not in self.schema.properties:
                    continue
                self.add(key, value, cleaned=cleaned, quiet=True)

    @property
    def _properties(self) -> Dict[str, List[str]]:  # type: ignore
        return {p: [s.value for s in v] for p, v in self._statements.items()}

    @property
    def statements(self) -> Generator[Statement, None, None]:
        for stmts in self._statements.values():
            yield from stmts

    @property
    def first_seen(self) -> Optional[datetime]:
        seen = (s.first_seen for s in self.statements if s.first_seen is not None)
        return min(seen, default=None)

    @property
    def last_seen(self) -> Optional[datetime]:
        seen = (s.last_seen for s in self.statements if s.last_seen is not None)
        return min(seen, default=None)

    def _make_statement(
        self,
        prop: str,
        value: str,
        schema: Optional[str] = None,
        dataset: Optional[str] = None,
        first_seen: Optional[datetime] = None,
        last_seen: Optional[datetime] = None,
        target: bool = False,
        external: bool = False,
    ) -> Statement:
        return Statement(
            entity_id=self.id,
            prop=prop,
            prop_type=self.schema.properties[prop].name,
            schema=schema or self.schema.name,
            value=value,
            dataset=dataset or self.default_dataset,
            first_seen=first_seen,
            target=target,
            external=external,
            canonical_id=self.id,
            last_seen=last_seen,
        )

    def add_statement(self, stmt: Statement) -> None:
        # TODO: change target, schema etc. based on data
        if self.schema.name != stmt.schema:
            self.schema = model.common_schema(self.schema, stmt.schema)
        if stmt.target is not None:
            self.target = self.target or stmt.target
        self.datasets.add(stmt.dataset)
        if stmt.prop != Statement.BASE:
            self._statements.setdefault(stmt.prop, set())
            self._statements[stmt.prop].add(stmt)

    def get(self, prop: P, quiet: bool = False) -> List[str]:
        prop_name = self._prop_name(prop, quiet=quiet)
        if prop_name is None or prop_name not in self._statements:
            return []
        return list({s.value for s in self._statements[prop_name]})

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

    def unsafe_add(
        self,
        prop: Property,
        value: Optional[str],
        cleaned: bool = False,
        fuzzy: bool = False,
        format: Optional[str] = None,
    ) -> None:
        if not cleaned and value is not None:
            value = prop.type.clean_text(value, fuzzy=fuzzy, format=format, proxy=self)
        if value is not None:
            stmt = self._make_statement(prop.name, value)
            self.add_statement(stmt)
        return None

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
        combined = set()
        for prop_name, statements in self._statements.items():
            prop = self.schema.properties[prop_name]
            if matchable and not prop.matchable:
                continue
            if prop.type == type_:
                for statement in statements:
                    combined.add(statement.value)
        return list(combined)

    @property
    def properties(self) -> Dict[str, List[str]]:
        return {p: list({s.value for s in vs}) for p, vs in self._statements.items()}

    def clone(self) -> "StatementProxy":
        data = {"schema": self.schema.name, "id": self.id}
        cloned = self.__class__.from_dict(self.schema.model, data)
        for stmt in self.statements:
            cloned.add_statement(stmt)
        return cloned

    def merge(self, other: "StatementProxy") -> "StatementProxy":
        for stmt in other.statements:
            stmt.canonical_id = self.id
            self.add_statement(stmt)
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["first_seen"] = self.first_seen
        data["last_seen"] = self.last_seen
        data["referents"] = list(self.referents)
        data["datasets"] = list(self.datasets)
        return data

    def __len__(self) -> int:
        raise NotImplemented
