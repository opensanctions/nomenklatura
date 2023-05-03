from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, TypeVar

import yaml
from followthemoney.types import registry

from nomenklatura.dataset.coverage import DataCoverage
from nomenklatura.dataset.publisher import DataPublisher
from nomenklatura.dataset.resource import DataResource
from nomenklatura.dataset.util import (
    Named,
    cleanup,
    string_list,
    type_check,
    type_require,
)
from nomenklatura.util import PathLike, iso_to_version

if TYPE_CHECKING:
    from nomenklatura.dataset.catalog import DataCatalog

DS = TypeVar("DS", bound="Dataset")


class Dataset(Named):
    """A unit of entities. A dataset is a set of data, sez W3C."""

    def __init__(self, catalog: "DataCatalog[DS]", data: Dict[str, Any]) -> None:
        self.catalog = catalog
        name = type_require(registry.string, data["name"])
        super().__init__(name)
        self.title = type_require(registry.string, data["title"])
        self.license = type_check(registry.url, data.get("license"))
        self.summary = type_check(registry.string, data.get("summary"))
        self.description = type_check(registry.string, data.get("description"))
        self.url = type_check(registry.url, data.get("url"))
        self.updated_at = type_check(registry.date, data.get("updated_at"))
        self.version = type_check(registry.string, data.get("version"))
        self.category = type_check(registry.string, data.get("category"))
        if self.version is None and self.updated_at is not None:
            self.version = iso_to_version(self.updated_at)

        pdata = data.get("publisher")
        self.publisher = DataPublisher(pdata) if pdata is not None else None

        cdata = data.get("coverage")
        self.coverage = DataCoverage(cdata) if cdata is not None else None
        self.resources: List[DataResource] = []
        for rdata in data.get("resources", []):
            if rdata is not None:
                self.resources.append(DataResource(rdata))

        # TODO: get rid of the legacy namings
        self._parents = set(string_list(data.get("parents", [])))
        self._parents.update(string_list(data.get("collections", [])))
        self._children = set(string_list(data.get("children", [])))
        self._children.update(string_list(data.get("datasets", [])))

    @property
    def children(self: DS) -> Set[DS]:
        children: Set[DS] = set()
        for child_name in self._children:
            children.add(self.catalog.require(child_name))
        for other in self.catalog.datasets:
            if self.name in other._parents:
                children.add(other)
        if self in children:
            children.remove(self)
        return children

    @cached_property
    def datasets(self: DS) -> Set[DS]:
        current: Set[DS] = set([self])
        for child in self.children:
            current.update(child.datasets)
        return current

    @property
    def parents(self: DS) -> Set[DS]:
        current: Set[DS] = set()
        for other in self.catalog.datasets:
            if self in other.datasets:
                current.add(other)
        if self in current:
            current.remove(self)
        return current

    @property
    def dataset_names(self) -> List[str]:
        return [d.name for d in self.datasets]

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "title": self.title,
            "license": self.license,
            "summary": self.summary,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "updated_at": self.updated_at,
            "category": self.category,
            "resources": [r.to_dict() for r in self.resources],
            "children": [c.name for c in self.children],
        }
        if self.coverage is not None:
            data["coverage"] = self.coverage.to_dict()
        if self.publisher is not None:
            data["publisher"] = self.publisher.to_dict()
        return cleanup(data)

    def get_resource(self, name: str) -> DataResource:
        for res in self.resources:
            if res.name == name:
                return res
        raise ValueError("No resource named %r!" % name)

    @classmethod
    def from_path(
        cls: Type[DS], path: PathLike, catalog: Optional["DataCatalog[DS]"] = None
    ) -> DS:
        from nomenklatura.dataset import DataCatalog

        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
            if catalog is None:
                catalog = DataCatalog(cls, {})
            return catalog.make_dataset(data)

    @classmethod
    def make(cls: Type[DS], data: Dict[str, Any]) -> DS:
        from nomenklatura.dataset import DataCatalog

        catalog = DataCatalog(cls, {})
        return catalog.make_dataset(data)
