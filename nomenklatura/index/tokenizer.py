from typing import Generic, Generator, Optional, Tuple, Set
from normality import WS, category_replace, ascii_text
from rigour.ids import StrictFormat
from rigour.names import tokenize_name
from rigour.names import remove_person_prefixes
from rigour.names.org_types import replace_org_types_display
from followthemoney import registry, Property, DS, SE


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


def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize a name by removing prefixes and suffixes."""
    if name is None:
        return None
    name = name.lower()
    name = " ".join(tokenize_name(name))
    name = ascii_text(name)
    if len(name) < 2:
        return None
    return name


class Tokenizer(Generic[DS, SE]):
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
            name_parts: Set[str] = set()
            # this needs to happen before the replacements
            text = remove_person_prefixes(value)
            for token in tokenize_name(text.lower(), token_min_length=3):
                name_parts.add(token)
            # Super hard-core string scrubbing
            cleaned = normalize_name(text)
            if cleaned is not None:
                cleaned = replace_org_types_display(cleaned, normalizer=normalize_name)
                yield type.name, cleaned
                for token in cleaned.split(WS):
                    name_parts.add(token)
            for part in name_parts:
                if len(part) > 2 and len(part) < 30:
                    yield NAME_PART_FIELD, part
            return
        if type == registry.identifier:
            clean_id = StrictFormat.normalize(value)
            if clean_id is not None:
                yield type.name, clean_id
            return
        if type in TEXT_TYPES:
            text = value.lower()
            replaced = category_replace(text)
            for word in replaced.split(WS):
                if len(word) >= 3:
                    yield WORD_FIELD, word

    def entity(self, entity: SE) -> Generator[Tuple[str, str], None, None]:
        # yield f"d:{entity.dataset.name}", 0.0
        for prop, value in entity.itervalues():
            for field, token in self.value(prop, value):
                yield field, token
