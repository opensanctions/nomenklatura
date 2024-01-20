from normality import WS
from rigour.ids import StrictFormat
from typing import Generic, Generator, Tuple
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.util import fingerprint_name
from nomenklatura.util import name_words, clean_text_basic

WORD_FIELD = "word"
NAME_PART_FIELD = "namepart"
SKIP_FULL = (
    # registry.name,
    registry.address,
    registry.text,
    registry.string,
    registry.number,
    registry.json,
)
TEXT_TYPES = (
    registry.text,
    registry.string,
    registry.address,
    registry.identifier,
    registry.name,
)


class Tokenizer(Generic[DS, CE]):
    def value(
        self, prop: Property, value: str
    ) -> Generator[Tuple[str, str], None, None]:
        """Perform type-specific token generation for a property value."""
        type = prop.type
        if not prop.matchable:
            return
        if type in (registry.url, registry.topic, registry.entity):
            return
        if type not in SKIP_FULL:
            token_value = value[:100].lower()
            yield type.name, token_value
        if type == registry.date:
            if len(value) > 4:
                yield type.name, value[:4]
            yield type.name, value[:10]
            return
        if type == registry.name:
            norm = fingerprint_name(value)
            if norm is not None:
                yield type.name, norm
                for token in norm.split(WS):
                    if len(token) > 2 and len(token) < 30:
                        yield NAME_PART_FIELD, token
            return
        if type == registry.identifier:
            clean_id = StrictFormat.normalize(value)
            if clean_id is not None:
                yield type.name, clean_id
            return
        if type in TEXT_TYPES:
            for word in name_words(clean_text_basic(value), min_length=3):
                yield WORD_FIELD, word

    def entity(self, entity: CE) -> Generator[Tuple[str, str], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        for prop, value in entity.itervalues():
            for field, token in self.value(prop, value):
                yield field, token
