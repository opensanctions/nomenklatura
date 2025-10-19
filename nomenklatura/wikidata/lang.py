import logging
from rigour.langs import PREFERRED_LANGS
from typing import Callable, Dict, Iterable, List, Optional, Any, Set
from followthemoney import registry, StatementEntity
from normality.cleaning import remove_unsafe_chars

log = logging.getLogger(__name__)


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
        if text is not None:
            text = remove_unsafe_chars(text)
        self.text = text
        self.lang: Optional[str] = None
        if lang is not None:
            self.lang = registry.language.clean_text(lang)
        if lang is not None and self.lang is None:
            # Language is given, but it is not one supported by the FtM ecosystem:
            self.text = None
        self.original = original or self.text

    def apply(
        self,
        entity: StatementEntity,
        prop: str,
        clean: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        if self.text is None:
            return
        clean_text = self.text if clean is None else clean(self.text)
        if clean_text is None or clean_text.strip() == "":
            return
        entity.add(prop, clean_text, lang=self.lang, original_value=self.original)

    def pack(self) -> Dict[str, Optional[str]]:
        data = {"t": self.text, "l": self.lang}
        if self.original is not None and self.original != self.text:
            data["o"] = self.original
        return data

    @classmethod
    def parse(cls, data: Dict[str, Optional[str]]) -> "LangText":
        return LangText(data["t"], data["l"], original=data.get("o"))

    @classmethod
    def pick(cls, texts: Iterable["LangText"]) -> Optional["LangText"]:
        for lang in PREFERRED_LANGS:
            for lt in texts:
                if lt.lang == lang:
                    return lt
        for lt in texts:
            return lt
        return None

    @classmethod
    def sorted(cls, texts: Iterable["LangText"]) -> List["LangText"]:
        def sort_key(lt: LangText) -> Any:
            if lt.lang is None or lt.lang not in PREFERRED_LANGS:
                index = len(PREFERRED_LANGS)
            else:
                index = PREFERRED_LANGS.index(lt.lang) + 1
            return (index, lt.text or "")

        return sorted(texts, key=sort_key)

    @classmethod
    def from_dict(cls, data: Dict[str, List[Dict[str, str]]]) -> Set["LangText"]:
        langs: Set[LangText] = set()
        for objs in data.values():
            if not isinstance(objs, list):
                objs = [objs]
            for obj in objs:
                value = obj["value"]
                if value is None:
                    continue
                lang = obj["language"]
                lt = LangText(value, lang, original=value)
                if lt.text is None:
                    continue
                langs.add(lt)
        return langs

    def __str__(self) -> str:
        if self.text is None:
            return ""
        return self.text

    def __hash__(self) -> int:
        return hash((self.text, self.lang, self.original))

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        return f"<LangText({self.text!r}, {self.lang!r}, {self.original!r})>"
