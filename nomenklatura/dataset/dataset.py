import yaml
import logging
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any, Dict, List, Optional, Set, Type, TypeVar
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
log = logging.getLogger(__name__)


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

        self._children = set(string_list(data.get("children", [])))
        self._children.update(string_list(data.get("datasets", [])))

        # FIXME: get rid of this
        self._children.update(string_list(data.get("scopes", [])))

    @cached_property
    def children(self: DS) -> Set[DS]:
        children: Set[DS] = set()
        for child_name in self._children:
            child = self.catalog.get(child_name)
            if child is None:
                log.error("Missing child dataset: %r (in %r)", child_name, self.name)
                continue
            if child == self:
                continue
            children.add(child)
        return children

    @cached_property
    def is_collection(self: "Dataset") -> bool:
        return len(self._children) > 0

    @property
    def datasets(self: DS) -> Set[DS]:
        current: Set[DS] = set([self])
        for child in self.children:
            current.update(child.datasets)
        return current

    @property
    def dataset_names(self: "Dataset") -> List[str]:
        return [d.name for d in self.datasets]

    @property
    def leaves(self: DS) -> Set[DS]:
        """All contained datasets which are not collections (can be 'self')."""
        return set([d for d in self.datasets if not d.is_collection])

    @property
    def leaf_names(self: "Dataset") -> Set[str]:
        return {d.name for d in self.leaves}

    def __eq__(self, other: Any) -> bool:
        try:
            return self.name == str(other.name)
        except AttributeError:
            return False

    def __lt__(self, other: Any) -> bool:
        try:
            return self.name < str(other.name)
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash(repr(self))

    def __repr__(self) -> str:
        return f"<Dataset({self.name})>"  # pragma: no cover

    def to_dict(self: "Dataset") -> Dict[str, Any]:
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
        }
        children = [c for c in self._children if c != self.name]
        if len(children):
            data["children"] = children
        datasets = [c.name for c in self.datasets if c != self]
        if len(datasets):
            data["datasets"] = datasets
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
