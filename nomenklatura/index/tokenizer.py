from typing import Generic, Optional
from typing import Any, Dict, Generator, Generic, Tuple
from normality import normalize, WS
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.index.util import split_ngrams
from nomenklatura.entity import DS, E
from nomenklatura.loader import Loader

SCHEMA_FIELD = "schema"
NGRAM_FIELD = "ngram"
WORD_FIELD = "word"
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
        return schema.name

    def value(
        self, type: PropertyType, value: str, fuzzy: bool = True
    ) -> Generator[Tuple[str, str], None, None]:
        """Perform type-specific token generation for a property value."""
        if type in (registry.url, registry.topic, registry.entity):
            return
        if type not in SKIP_FULL:
            token_value = value[:100].lower()
            yield type.name, token_value
        if type == registry.date and len(value) > 4:
            yield type.name, value[:4]
        if type in TEXT_TYPES:
            norm = normalize(value, ascii=True, lowercase=True)
            if norm is None:
                return
            tokens = norm.split(WS)
            if type == registry.name:
                yield type.name, " ".join(sorted(tokens))
            for token in tokens:
                yield WORD_FIELD, token
                if type == registry.name:
                    yield type.name, token

                if fuzzy:
                    for ngram in split_ngrams(token, 2, 3):
                        yield NGRAM_FIELD, ngram

    def entity(
        self,
        entity: E,
        loader: Optional[Loader[DS, E]] = None,
        fuzzy: bool = True,
    ) -> Generator[Tuple[str, str], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        yield SCHEMA_FIELD, self.schema_token(entity.schema)
        for prop, value in entity.itervalues():
            for field, token in self.value(prop.type, value, fuzzy=fuzzy):
                yield field, token
        if loader is not None:
            # Index Address, Identification, Sanction, etc.:
            for prop, other in loader.get_adjacent(entity):
                for prop, value in other.itervalues():
                    if prop.hidden or not prop.matchable:
                        continue
                    # Skip interval dates (not to be mixed up with other dates)
                    if prop.type in (registry.date, registry.name):
                        continue
                    for field, token in self.value(prop.type, value, fuzzy=fuzzy):
                        yield field, token
