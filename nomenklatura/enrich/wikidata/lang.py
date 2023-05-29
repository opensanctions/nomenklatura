from typing import Counter, Dict, Optional
from followthemoney.types import registry


DEFAULT_LANG = "en"
ALT_LANG_ORDER = ["es", "fr", "de", "ru"]


class LangText(object):
    __slots__ = ["text", "lang"]

    def __init__(self, text: str, lang: Optional[str]):
        self.text = text
        self.lang = registry.language.clean(lang)

    def __hash__(self):
        return hash((self.text, self.lang))

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __repr__(self):
        return f"{self.text!r}@{self.lang or '???'}"

    def pack(self) -> str:
        lang = self.lang or ""
        return f"{lang}:{self.text}"

    @classmethod
    def parse(self, packed):
        lang, text = packed.split(":", 1)
        if not len(lang):
            lang = None
        return LangText(text, lang)


def pick_lang_text(values: Dict[str, str]) -> Optional[LangText]:
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

    return None


def pick_obj_lang(items: Dict[str, Dict[str, str]]) -> Optional[LangText]:
    values = {}
    for label in items.values():
        value = label.get("value")
        if value is not None:
            values[label.get("language", "")] = value
    return pick_lang_text(values)
