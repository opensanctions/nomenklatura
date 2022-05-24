from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
from typing import Type, TypeVar
from followthemoney.model import Model
from followthemoney.proxy import EntityProxy

from nomenklatura.dataset import DS

if TYPE_CHECKING:
    from nomenklatura.loader import Loader

CE = TypeVar("CE", bound="CompositeEntity")


class CompositeEntity(EntityProxy):
    """An entity object that can link to a set of datasets that it is sourced from."""

    def __init__(
        self,
        model: Model,
        data: Dict[str, Any],
        key_prefix: Optional[str] = None,
        cleaned: bool = True,
    ) -> None:
        self.datasets: Set[str] = set()
        """The set of datasets from which information in this entity is derived."""

        self.referents: Set[str] = set()
        """The IDs of all entities which are included in this canonical entity."""
        super().__init__(model, data, key_prefix=key_prefix, cleaned=cleaned)

    def merge(self: CE, other: CE) -> CE:
        """Merge another entity proxy into this one. For composite entities, this
        will update the datasets and referents data accordingly."""
        merged = super().merge(other)
        merged.referents.update(other.referents)
        merged.datasets.update(other.datasets)
        return merged

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["referents"] = list(self.referents)
        data["datasets"] = list(self.datasets)
        return data

    def _to_nested_dict(
        self: CE, loader: "Loader[DS, CE]", depth: int, path: List[str]
    ) -> Dict[str, Any]:
        next_depth = depth if self.schema.edge else depth - 1
        next_path = path + [self.id]
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
        obj = super().from_dict(model, data, cleaned=cleaned)
        obj.referents.update(data.get("referents", []))
        obj.datasets.update(data.get("datasets", []))
        return obj
