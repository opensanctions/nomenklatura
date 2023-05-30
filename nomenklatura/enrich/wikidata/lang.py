import json
from typing import Counter, Dict, Optional
from followthemoney.types import registry

from nomenklatura.entity import CE


DEFAULT_LANG = "en"
ALT_LANG_ORDER = ["es", "fr", "de", "ru"]


class LangText(object):
    __slots__ = ["text", "lang", "original"]

    def __init__(
        self,
        text: Optional[str],
        lang: Optional[str] = None,
        original: Optional[str] = None,
    ):
        if text is None or len(text.strip()) == 0:
            text = None
        self.text = text
        self.lang = registry.language.clean(lang)
        self.original = original

    def __hash__(self):
        return hash((self.text, self.lang))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __repr__(self):
        if self.text is None:
            return "<empty>"
        return f"{self.text!r}@{self.lang or '???'}"

    def apply(self, entity: CE, prop: str):
        if self.text is not None:
            entity.add(prop, self.text, lang=self.lang, original_value=self.original)

    def pack(self) -> str:
        return json.dumps({"t": self.text, "l": self.lang, "o": self.original})

    @classmethod
    def parse(self, packed):
        data = json.loads(packed)
        return LangText(data["t"], data["l"], original=data["o"])


def pick_lang_text(values: Dict[str, str]) -> LangText:
    """Pick a text value from a dict of language -> text."""
    value = values.get(DEFAULT_LANG)
    if value is not None:
        return LangText(value, DEFAULT_LANG)

    counter = Counter[str]()
    counter.update(values.values())
    for (value, count) in counter.most_common(1):
        if count > 1:
            for lang, v in values.items():
                if v == value:
                    return LangText(value, lang)

    for lang in ALT_LANG_ORDER:
        value = values.get(lang)
        if value is not None:
            return LangText(value, lang)

    for lang, value in values.items():
        if value is not None:
            return LangText(value, lang)

    return LangText(None, None)


def pick_obj_lang(items: Dict[str, Dict[str, str]]) -> LangText:
    values = {}
    for label in items.values():
        value = label.get("value")
        if value is not None:
            values[label.get("language", "")] = value
    return pick_lang_text(values)
