import fingerprints
from typing import Generic, Optional
from typing import Any, Dict, Generator, Generic, Tuple, cast
from normality import normalize, WS
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.index.util import ngrams
from nomenklatura.loader import DS, E, Loader

TYPE_WEIGHTS = {
    registry.name: 2.0,
    registry.country: 1.5,
    registry.date: 1.5,
    registry.language: 0.7,
    registry.iban: 3.0,
    registry.phone: 3.0,
    registry.email: 3.0,
    registry.entity: 0.0,
    registry.topic: 2.1,
    registry.address: 2.5,
    registry.identifier: 2.5,
}
TEXT_TYPES = (
    registry.name,
    registry.text,
    registry.string,
    registry.address,
    registry.identifier,
)


class Tokenizer(Generic[DS, E]):
    def schema_token(self, schema: Schema) -> str:
        return f"s:{schema.name}"

    def value(
        self, type: PropertyType, value: str
    ) -> Generator[Tuple[str, float], None, None]:
        """Perform type-specific token generation for a property value."""
        if type == registry.entity:
            return
        node_id = type.node_id(value)
        type_weight = TYPE_WEIGHTS.get(type, 1.0)
        if node_id is not None:
            yield node_id, type_weight
        if type == registry.date and len(value) > 3:
            yield f"y:{value[:4]}", 1.0
        if type in TEXT_TYPES:
            norm = normalize(value, ascii=True, lowercase=True)
            if norm is None:
                return
            for token in norm.split(WS):
                yield f"w:{token}", 0.7
            if type == registry.name:
                fp = type.node_id_safe(fingerprints.generate(norm))
                if fp is not None and fp != node_id:
                    yield fp, type_weight * 0.8
                for token in ngrams(norm, 2, 4):
                    yield f"g:{token}", 0.5

    def entity(
        self, entity: E, loader: Optional[Loader[DS, E]] = None
    ) -> Generator[Tuple[str, float], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        yield self.schema_token(entity.schema), 0.0
        for prop, value in entity.itervalues():
            for token, weight in self.value(prop.type, value):
                yield token, weight
        if loader is not None:
            # Index Address, Identification, Sanction, etc.:
            for prop, other in loader.get_adjacent(entity):
                for prop, value in other.itervalues():
                    # Skip interval dates (not to be mixed up with other dates)
                    if prop.type == registry.date:
                        continue
                    for token, weight in self.value(prop.type, value):
                        yield token, weight * 0.8
