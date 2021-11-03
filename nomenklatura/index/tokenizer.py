from typing import Generic, Optional
from typing import Any, Dict, Generator, Generic, Tuple
from normality import normalize, WS
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.index.util import split_ngrams
from nomenklatura.entity import DS, E
from nomenklatura.loader import Loader

TYPE_WEIGHTS = {
    registry.name: 3.0,
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
SKIP_FULL = (
    registry.name,
    registry.address,
    registry.text,
    registry.string,
    registry.number,
    registry.json,
)
TEXT_TYPES = (
    *SKIP_FULL,
    registry.identifier,
)


class Tokenizer(Generic[DS, E]):
    def schema_token(self, schema: Schema) -> str:
        return f"s:{schema.name}"

    def value(
        self, type: PropertyType, value: str, fuzzy: bool = True
    ) -> Generator[Tuple[str, float], None, None]:
        """Perform type-specific token generation for a property value."""
        if type in (registry.url, registry.topic, registry.entity):
            return
        weight = TYPE_WEIGHTS.get(type, 1.0)
        if type not in SKIP_FULL:
            token_value = value[:100].lower()
            token = f"{type.name[:2]}:{token_value}"
            yield token, weight
        if type == registry.date and len(value) > 4:
            yield f"da:{value[:4]}", 1.0
        if type in TEXT_TYPES:
            norm = normalize(value, ascii=True, lowercase=True)
            if norm is None:
                return
            for token in norm.split(WS):
                yield f"w:{token}", weight
                if type == registry.name:
                    yield f"na:{token}", weight

                if fuzzy:
                    for ngram in split_ngrams(token, 3, 4):
                        yield f"w:{ngram}", 0.5

    def entity(
        self,
        entity: E,
        loader: Optional[Loader[DS, E]] = None,
        fuzzy: bool = True,
    ) -> Generator[Tuple[str, float], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        yield self.schema_token(entity.schema), 0.0
        for prop, value in entity.itervalues():
            for token, weight in self.value(prop.type, value, fuzzy=fuzzy):
                yield token, weight
        if loader is not None:
            # Index Address, Identification, Sanction, etc.:
            for prop, other in loader.get_adjacent(entity):
                for prop, value in other.itervalues():
                    # Skip interval dates (not to be mixed up with other dates)
                    if prop.type == registry.date:
                        continue
                    for token, weight in self.value(prop.type, value, fuzzy=fuzzy):
                        yield token, weight * 0.8
