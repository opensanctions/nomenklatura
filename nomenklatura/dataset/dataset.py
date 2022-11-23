import yaml
from typing import Any, Dict, TypeVar, Optional, List
from followthemoney.types import registry

from nomenklatura.dataset.resource import DataResource
from nomenklatura.dataset.publisher import DataPublisher
from nomenklatura.dataset.coverage import DataCoverage
from nomenklatura.dataset.util import Named, cleanup
from nomenklatura.dataset.util import type_check, type_require
from nomenklatura.util import iso_to_version, PathLike

DS = TypeVar("DS", bound="Dataset")


class Dataset(Named):
    """A unit of entities. A dataset is a set of data, sez W3C."""

    def __init__(
        self,
        name: str,
        title: str,
        license: Optional[str] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        url: Optional[str] = None,
        version: Optional[str] = None,
        updated_at: Optional[str] = None,
        publisher: Optional[DataPublisher] = None,
        coverage: Optional[DataCoverage] = None,
        resources: List[DataResource] = [],
    ) -> None:
        super().__init__(name)
        self.title = title
        self.license = license
        self.summary = summary
        self.description = description
        self.url = url
        self.updated_at = updated_at
        if version is None:
            version = iso_to_version(updated_at)
        self.version = version
        self.publisher = publisher
        self.coverage = coverage
        self.resources = resources

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "title": self.title,
            "license": self.license,
            "summary": self.summary,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "updated_at": self.updated_at,
            "publisher": self.publisher,
            "coverage": self.coverage,
            "resources": self.resources,
        }
        return cleanup(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dataset":
        pdata = data.get("publisher")
        publisher = DataPublisher.from_dict(pdata) if pdata is not None else None
        cdata = data.get("coverage")
        coverage = DataCoverage.from_dict(cdata) if cdata is not None else None
        resources: List[DataResource] = []
        for rdata in data.get("resources", []):
            if rdata is not None:
                resources.append(DataResource.from_dict(rdata))
        return cls(
            name=type_require(registry.string, data["name"]),
            title=type_require(registry.string, data["title"]),
            license=type_check(registry.url, data.get("license")),
            summary=type_check(registry.string, data.get("summary")),
            description=type_check(registry.string, data.get("description")),
            url=type_check(registry.url, data.get("url")),
            version=type_check(registry.string, data.get("version")),
            updated_at=type_check(registry.date, data.get("updated_at")),
            publisher=publisher,
            coverage=coverage,
            resources=resources,
        )

    @classmethod
    def from_path(cls, path: PathLike) -> "Dataset":
        with open(path, "r") as fh:
            return cls.from_dict(yaml.safe_load(fh))
