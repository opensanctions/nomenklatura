from typing import Counter, Dict, Optional, Tuple


DEFAULT_LANG = "en"
ALT_LANG_ORDER = ["es", "fr", "de", "ru"]


class LangText(object):
    __slots__ = ["text", "lang"]

    def __init__(self, text: str, lang: str):
        self.text = text
        self.lang = lang


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
