from typing import Generic, Optional
from typing import Any, Dict, Generator, Generic, Tuple, cast
from normality import normalize, WS
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.index.util import ngrams
from nomenklatura.loader import DS, E, Loader

TYPE_WEIGHTS = {
    registry.country: 0.2,
    registry.date: 0.2,
    registry.language: 0.2,
    registry.iban: 2.0,
    registry.phone: 2.0,
    registry.email: 2.0,
    registry.entity: 0.0,
    registry.topic: 0.1,
    registry.address: 1.2,
    registry.identifier: 1.5,
}
TEXT_TYPES = (registry.name, registry.text, registry.string, registry.address)


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
        if node_id is not None:
            type_weight = TYPE_WEIGHTS.get(type, 1.0)
            yield node_id, type_weight
        if type == registry.date and len(value) > 3:
            yield f"y:{value[:4]}", 0.7
        if type in TEXT_TYPES:
            norm = normalize(value, ascii=True, lowercase=True)
            if norm is None:
                return
            for token in norm.split(WS):
                yield f"w:{token}", 0.5
            if type == registry.name:
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
                        yield token, weight * 0.7
