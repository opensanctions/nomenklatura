from nomenklatura.dataset.dataset import Dataset, DS
from nomenklatura.dataset.catalog import DataCatalog
from nomenklatura.dataset.resource import DataResource
from nomenklatura.dataset.publisher import DataPublisher
from nomenklatura.dataset.coverage import DataCoverage

DefaultDataset = Dataset.make({"name": "default", "title": "default"})

__all__ = [
    "Dataset",
    "DefaultDataset",
    "DataCatalog",
    "DataResource",
    "DataPublisher",
    "DataCoverage",
    "DS",
]
