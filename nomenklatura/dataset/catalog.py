import yaml
from typing import Optional, Dict, Any, Generic, Set, Type, List
from followthemoney.types import registry

from nomenklatura.dataset.dataset import DS
from nomenklatura.exceptions import MetadataException
from nomenklatura.dataset.util import type_check
from nomenklatura.util import PathLike


class DataCatalog(Generic[DS]):
    def __init__(self, dataset_type: Type[DS], data: Dict[str, Any]) -> None:
        self.dataset_type = dataset_type
        self.datasets: List[DS] = []
        for ddata in data["datasets"]:
            self.datasets.append(self.dataset_type(self, ddata))  # type: ignore
        self.updated_at = type_check(registry.date, data.get("updated_at"))

    def get(self, name: str) -> Optional[DS]:
        for ds in self.datasets:
            if ds.name == name:
                return ds
        return None

    def require(self, name: str) -> DS:
        dataset = self.get(name)
        if dataset is None:
            raise MetadataException("No such dataset: %s" % name)
        return dataset

    def has(self, name: str) -> bool:
        return name in self.names

    @property
    def names(self) -> Set[str]:
        return {d.name for d in self.datasets}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasets": [d.to_dict() for d in self.datasets],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_path(cls, dataset_type: Type[DS], path: PathLike) -> "DataCatalog[DS]":
        with open(path, "r") as fh:
            return cls(dataset_type, yaml.safe_load(fh))
