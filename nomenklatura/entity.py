from typing import Any, Dict, Optional, Set, cast
from followthemoney.model import Model
from followthemoney.proxy import EntityProxy

from nomenklatura.dataset import Dataset


class CompositeEntity(EntityProxy):
    """An entity object that can link to a set of datasets that it is sourced from."""

    def __init__(
        self,
        model: Model,
        data: Dict[str, Any],
        key_prefix: Optional[str] = None,
        cleaned: bool = True,
    ) -> None:
        super().__init__(model, data, key_prefix=key_prefix, cleaned=cleaned)
        self.datasets: Set[Dataset] = set()
        """The set of datasets from which information in this entity is derived."""

        self.referents: Set[str] = set()
        """The IDs of all entities which are included in this canonical entity."""

    def merge(self, other: "EntityProxy") -> "CompositeEntity":
        """Merge another entity proxy into this one. For composite entities, this
        will update the datasets and referents data accordingly."""
        merged = cast(CompositeEntity, super().merge(other))
        if isinstance(other, CompositeEntity):
            merged.referents.update(other.referents)
            merged.datasets.update(other.datasets)
        return merged

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["referents"] = list(self.referents)
        data["datasets"] = [d.name for d in self.datasets]
        return data
