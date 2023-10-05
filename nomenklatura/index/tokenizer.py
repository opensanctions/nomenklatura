from normality import WS
from typing import Generic, Generator, Tuple
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.util import fingerprint_name, clean_identifier
from nomenklatura.util import names_word_list, normalize_name

WORD_FIELD = "word"
NAME_PART_FIELD = "namepart"
SKIP_FULL = (
    registry.name,
    registry.address,
    registry.text,
    registry.string,
    registry.number,
    registry.json,
)
TEXT_TYPES = (registry.text, registry.string, registry.address)


class Tokenizer(Generic[DS, CE]):
    def value(
        self, type: PropertyType, value: str
    ) -> Generator[Tuple[str, str], None, None]:
        """Perform type-specific token generation for a property value."""
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
            clean_id = clean_identifier(value)
            if clean_id is not None:
                yield type.name, clean_id
            return
        if type in TEXT_TYPES:
            for word in names_word_list(
                [value],
                normalizer=normalize_name,
                min_length=3,
            ):
                yield WORD_FIELD, word

    def entity(self, entity: CE) -> Generator[Tuple[str, str], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        for prop, value in entity.itervalues():
            for field, token in self.value(prop.type, value):
                yield field, token
