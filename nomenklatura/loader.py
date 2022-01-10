import json
import logging
import aiofiles
from nomenklatura.resolver import Resolver
from typing import AsyncGenerator, Dict, Generic, Iterable, List, Optional, Tuple
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

    async def get_entity(self, id: str) -> Optional[E]:
        raise NotImplemented

    async def get_inverted(self, id: str) -> AsyncGenerator[Tuple[Property, E], None]:
        if False:
            yield
        raise NotImplemented

    async def entities(self) -> AsyncGenerator[E, None]:
        if False:
            yield
        raise NotImplemented

    async def count(self) -> int:
        raise NotImplemented

    async def get_adjacent(
        self, entity: E, inverted: bool = True
    ) -> AsyncGenerator[Tuple[Property, E], None]:
        for prop, value in entity.itervalues():
            if prop.type == registry.entity:
                child = await self.get_entity(value)
                if child is not None:
                    yield prop, child

        if inverted:
            async for prop, adjacent in self.get_inverted(entity.id):
                yield prop, adjacent


class MemoryLoader(Loader[DS, E]):
    """Load entities from the given iterable of entities."""

    def __init__(
        self, dataset: DS, entities: Iterable[E], resolver: Optional[Resolver[E]] = None
    ) -> None:
        super().__init__(dataset)
        self.resolver = resolver or Resolver[E]()
        self._entities: Dict[str, E] = {}
        self.inverted: Dict[str, List[Tuple[Property, str]]] = {}
        log.info("Loading %r to memory...", dataset)
        for entity in entities:
            self.resolver.apply(entity)
            if entity.id in self._entities:
                self._entities[entity.id].merge(entity)
            else:
                self._entities[entity.id] = entity
            for prop, value in entity.itervalues():
                if prop.type != registry.entity:
                    continue
                if value not in self.inverted:
                    self.inverted[value] = []
                if prop.reverse is not None:
                    self.inverted[value].append((prop.reverse, entity.id))

    async def get_entity(self, id: str) -> Optional[E]:
        canonical_id = self.resolver.get_canonical(id)
        return self._entities.get(canonical_id)

    async def get_inverted(self, id: str) -> AsyncGenerator[Tuple[Property, E], None]:
        canonical_id = self.resolver.get_canonical(id)
        for prop, entity_id in self.inverted.get(canonical_id, []):
            entity = await self.get_entity(entity_id)
            if entity is not None:
                yield prop, entity

    async def entities(self) -> AsyncGenerator[E, None]:
        for entity in self._entities.values():
            yield entity

    async def count(self) -> int:
        return len(self._entities)

    def __repr__(self) -> str:
        return f"<MemoryLoader({self.dataset!r}, {len(self._entities)})>"


class FileLoader(MemoryLoader[Dataset, CompositeEntity]):
    """Read a given file path into an in-memory entity loader."""

    def __init__(
        self,
        dataset: Dataset,
        entities: List[CompositeEntity],
        path: PathLike,
        resolver: Optional[Resolver[CompositeEntity]] = None,
    ) -> None:
        self.path = path
        super().__init__(dataset, entities, resolver)

    @classmethod
    async def from_file(
        cls, path: PathLike, resolver: Optional[Resolver[CompositeEntity]] = None
    ) -> "FileLoader":
        dataset = Dataset(path.stem, path.stem)
        async with aiofiles.open(path, "r") as fh:
            entities: List[CompositeEntity] = []
            while True:
                line = await fh.readline()
                if not line:
                    break
                data = json.loads(line)
                proxy = CompositeEntity(model, data, cleaned=True)
                proxy.datasets.add(dataset)
                entities.append(proxy)
        return cls(dataset, entities, path, resolver=resolver)

    def __repr__(self) -> str:
        return f"<FileLoader({self.path!r}, {len(self._entities)})>"
