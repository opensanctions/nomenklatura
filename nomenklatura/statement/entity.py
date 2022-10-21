from datetime import datetime
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generator,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    Type,
    TypeVar,
    cast,
)
import warnings
from itertools import product
from banal import ensure_dict

from followthemoney import model
from followthemoney.exc import InvalidData
from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from followthemoney.property import Property
from followthemoney.rdf import SKOS, RDF, Literal, URIRef, Identifier
from followthemoney.util import sanitize_text, gettext
from followthemoney.util import merge_context, value_list, make_entity_id
from followthemoney.proxy import P

if TYPE_CHECKING:
    from followthemoney.model import Model

from nomenklatura.entity import CompositeEntity, CE
from nomenklatura.statement.model import S, Statement

log = logging.getLogger(__name__)


class StatementProxy(CompositeEntity, Generic[S]):
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
        statement_type: Type[Statement] = Statement,
        default_dataset: str = "default",
    ):
        data = dict(data or {})
        schema = model.get(data.pop("schema", None))
        if schema is None:
            raise InvalidData(gettext("No schema for entity."))
        self.schema = schema
        self.target: Optional[bool] = data.pop("target", None)
        self.default_dataset = default_dataset
        self.statement_type = statement_type
        self.key_prefix = key_prefix
        self.id = data.pop("id", None)
        self._statements: Dict[str, Set[S]] = {}

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
    def statements(self) -> Generator[S, None, None]:
        for stmts in self._statements.values():
            yield from stmts

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
    ) -> S:
        return self.statement_type(
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

    def add_statement(self, stmt: S) -> None:
        # TODO: change target, schema etc. based on data
        self.schema = model.common_schema(self.schema, stmt.schema)
        if stmt.target is not None:
            self.target = self.target or stmt.target
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
        """Return a mapping of the properties and set values of the entity."""
        return {p: list(vs) for p, vs in self._properties.items()}

    def clone(self: CE) -> CE:
        """Make a deep copy of the current entity proxy."""
        return self.__class__.from_dict(self.schema.model, self.to_dict())

    def merge(self: CE, other: CE) -> CE:
        """Merge another entity proxy into this one. This will try and find
        the common schema between both entities and then add all property
        values from the other entity into this one."""
        model = self.schema.model
        self.id = self.id or other.id
        try:
            self.schema = model.common_schema(self.schema, other.schema)
        except InvalidData as e:
            msg = "Cannot merge entities with id %s: %s"
            raise InvalidData(msg % (self.id, e))

        self.context = merge_context(self.context, other.context)
        for prop, values in other._properties.items():
            self.add(prop, values, cleaned=True, quiet=True)
        return self

    def __len__(self) -> int:
        raise NotImplemented
