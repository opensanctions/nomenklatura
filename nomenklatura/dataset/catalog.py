from typing import List, Optional, Dict, Any

from nomenklatura.dataset.dataset import Dataset


class DataCatalog(object):
    def __init__(self, datasets: List[Dataset] = [], updated_at: Optional[str] = None):
        self.datasets = datasets
        self.updated_at = updated_at

    def get(self, name: str) -> Optional[Dataset]:
        for ds in self.datasets:
            if ds.name == name:
                return ds
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datasets": [d.to_dict() for d in self.datasets],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataCatalog":
        datasets = [Dataset.from_dict(d) for d in data["datasets"]]
        return cls(datasets=datasets, updated_at=data.get("updated_at"))
