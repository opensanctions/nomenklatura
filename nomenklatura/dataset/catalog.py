import yaml
from typing import List, Optional, Dict, Any

from nomenklatura.dataset.dataset import Dataset
from nomenklatura.exceptions import MetadataException
from nomenklatura.util import PathLike


class DataCatalog(object):
    def __init__(self, datasets: List[Dataset] = [], updated_at: Optional[str] = None):
        self.datasets = datasets
        self.updated_at = updated_at

    def get(self, name: str) -> Optional[Dataset]:
        for ds in self.datasets:
            if ds.name == name:
                return ds
        return None

    def require(cls, name) -> Dataset:
        dataset = cls.get(name)
        if dataset is None:
            raise MetadataException("No such dataset: %s" % name)
        return dataset

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasets": [d.to_dict() for d in self.datasets],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataCatalog":
        datasets = [Dataset.from_dict(d) for d in data["datasets"]]
        return cls(datasets=datasets, updated_at=data.get("updated_at"))

    @classmethod
    def from_path(cls, path: PathLike) -> "DataCatalog":
        with open(path, "r") as fh:
            return cls.from_dict(yaml.safe_load(fh))
