import json
import logging
from pathlib import Path
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

from nomenklatura.resolver import Resolver
from nomenklatura.dataset import Dataset, DS
from nomenklatura.entity import CompositeEntity, CE
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


class Loader(Generic[DS, CE]):
    """An abstract base class for implementing"""

    def __init__(self, dataset: DS):
        self.dataset = dataset

    def get_entity(self, id: str) -> Optional[CE]:
        raise NotImplemented

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        raise NotImplemented

    def __iter__(self) -> Iterator[CE]:
        raise NotImplemented

    def __len__(self) -> int:
        raise NotImplemented

    def get_adjacent(
        self, entity: CE, inverted: bool = True
    ) -> Generator[Tuple[Property, CE], None, None]:
        for prop, value in entity.itervalues():
            if prop.type == registry.entity:
                child = self.get_entity(value)
                if child is not None:
                    yield prop, child

        if inverted:
            for prop, adjacent in self.get_inverted(entity.id):
                yield prop, adjacent


class MemoryLoader(Loader[DS, CE]):
    """Load entities from the given iterable of entities."""

    def __init__(
        self,
        dataset: DS,
        entities: Iterable[CE],
        resolver: Optional[Resolver[CE]] = None,
    ) -> None:
        super().__init__(dataset)
        self.resolver = resolver or Resolver[CE]()
        self.entities: Dict[str, CE] = {}
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

    def get_entity(self, id: str) -> Optional[CE]:
        canonical_id = self.resolver.get_canonical(id)
        return self.entities.get(canonical_id)

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        canonical_id = self.resolver.get_canonical(id)
        for prop, entity_id in self.inverted.get(canonical_id, []):
            entity = self.get_entity(entity_id)
            if entity is not None:
                yield prop, entity

    def __iter__(self) -> Iterator[CE]:
        return iter(self.entities.values())

    def __len__(self) -> int:
        return len(self.entities)

    def __repr__(self) -> str:
        return f"<MemoryLoader({self.dataset!r}, {len(self.entities)})>"


class FileLoader(MemoryLoader[Dataset, CompositeEntity]):
    """Read a given file path into an in-memory entity loader."""

    def __init__(
        self, path: Path, resolver: Optional[Resolver[CompositeEntity]] = None
    ) -> None:
        dataset = Dataset(path.stem, path.stem)
        entities = self.read_file(dataset, path)
        super().__init__(dataset, entities, resolver=resolver)
        self.path = path

    def read_file(
        self, dataset: Dataset, path: Path
    ) -> Generator[CompositeEntity, None, None]:
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                data = json.loads(line)
                proxy = CompositeEntity.from_dict(model, data)
                proxy.datasets.add(dataset.name)
                yield proxy

    def __repr__(self) -> str:
        return f"<FileLoader({self.path!r}, {len(self.entities)})>"
