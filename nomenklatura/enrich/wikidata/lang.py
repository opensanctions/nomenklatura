from typing import Callable, Counter, Dict, Optional, Any
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
    ) -> None:
        if text is None or len(text.strip()) == 0:
            text = None
        self.text = text
        self.lang = registry.language.clean(lang)
        if lang is not None and self.lang is None:
            self.text = None    
        self.original = original

    def __hash__(self) -> int:
        return hash((self.text, self.lang))

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        if self.text is None:
            return "<empty>"
        return f"{self.text!r}@{self.lang or '???'}"

    def apply(self, entity: CE, prop: str, clean: Optional[Callable[[str], str]] = None) -> None:
        if self.text is None:
            return
        clean_text = self.text if clean is None else clean(self.text)
        if clean_text == "":
            return
        entity.add(prop, clean_text, lang=self.lang, original_value=self.original)

    def pack(self) -> Dict[str, Optional[str]]:
        return {"t": self.text, "l": self.lang, "o": self.original}

    @classmethod
    def parse(self, data: Dict[str, Optional[str]]) -> "LangText":
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
