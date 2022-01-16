import json
import logging
from nomenklatura.resolver import Resolver
from typing import (
    Dict,
    Generator,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
)
from followthemoney.types import registry
from followthemoney.property import Property
from followthemoney import model

from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity, DS, E
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


class Loader(Generic[DS, E]):
    """An abstract base class for implementing"""

    def __init__(self, dataset: DS):
        self.dataset = dataset

    def get_entity(self, id: str) -> Optional[E]:
        raise NotImplemented

    def get_inverted(self, id: str) -> Generator[Tuple[Property, E], None, None]:
        raise NotImplemented

    def __iter__(self) -> Iterator[E]:
        raise NotImplemented

    def __len__(self) -> int:
        raise NotImplemented

    def get_adjacent(
        self, entity: E, inverted: bool = True
    ) -> Generator[Tuple[Property, E], None, None]:
        for prop, value in entity.itervalues():
            if prop.type == registry.entity:
                child = self.get_entity(value)
                if child is not None:
                    yield prop, child

        if inverted:
            for prop, adjacent in self.get_inverted(entity.id):
                yield prop, adjacent


class MemoryLoader(Loader[DS, E]):
    """Load entities from the given iterable of entities."""

    def __init__(
        self, dataset: DS, entities: Iterable[E], resolver: Optional[Resolver[E]] = None
    ) -> None:
        super().__init__(dataset)
        self.resolver = resolver or Resolver[E]()
        self.entities: Dict[str, E] = {}
        self.inverted: Dict[str, List[Tuple[Property, str]]] = {}
        log.info("Loading %r to memory...", dataset)
        for entity in entities:
            self.resolver.apply(entity)
            if entity.id in self.entities:
                self.entities[entity.id].merge(entity)
            else:
                self.entities[entity.id] = entity
            for prop, value in entity.itervalues():
                if prop.type != registry.entity:
                    continue
                if value not in self.inverted:
                    self.inverted[value] = []
                if prop.reverse is not None:
                    self.inverted[value].append((prop.reverse, entity.id))

    def get_entity(self, id: str) -> Optional[E]:
        canonical_id = self.resolver.get_canonical(id)
        return self.entities.get(canonical_id)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, E], None, None]:
        canonical_id = self.resolver.get_canonical(id)
        for prop, entity_id in self.inverted.get(canonical_id, []):
            entity = self.get_entity(entity_id)
            if entity is not None:
                yield prop, entity

    def __iter__(self) -> Iterator[E]:
        return iter(self.entities.values())

    def __len__(self) -> int:
        return len(self.entities)

    def __repr__(self) -> str:
        return f"<MemoryLoader({self.dataset!r}, {len(self.entities)})>"


class FileLoader(MemoryLoader[Dataset, CompositeEntity]):
    """Read a given file path into an in-memory entity loader."""

    def __init__(
        self, path: PathLike, resolver: Optional[Resolver[CompositeEntity]] = None
    ) -> None:
        dataset = Dataset(path.stem, path.stem)
        entities = self.read_file(dataset, path)
        super().__init__(dataset, entities, resolver=resolver)
        self.path = path

    def read_file(
        self, dataset: Dataset, path: PathLike
    ) -> Generator[CompositeEntity, None, None]:
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                data = json.loads(line)
                proxy = CompositeEntity(model, data, cleaned=True)
                proxy.datasets.add(dataset)
                yield proxy

    def __repr__(self) -> str:
        return f"<FileLoader({self.path!r}, {len(self.entities)})>"
