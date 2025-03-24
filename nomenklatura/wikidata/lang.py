import logging
from rigour.langs import PREFFERED_LANGS
from typing import Callable, Dict, Iterable, List, Optional, Any, Set
from followthemoney.types import registry
from normality.cleaning import remove_unsafe_chars

from nomenklatura.entity import CE

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
        self.text = remove_unsafe_chars(text)
        self.lang = registry.language.clean(lang)
        if lang is not None and self.lang is None:
            # Language is given, but it is not one supported by the FtM ecosystem:
            self.text = None
        self.original = original

    def apply(
        self,
        entity: CE,
        prop: str,
        clean: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        if self.text is None:
            return
        clean_text = self.text if clean is None else clean(self.text)
        if clean_text is None or clean_text == "":
            return
        entity.add(prop, clean_text, lang=self.lang, original_value=self.original)

    def pack(self) -> Dict[str, Optional[str]]:
        return {"t": self.text, "l": self.lang, "o": self.original}

    @classmethod
    def parse(cls, data: Dict[str, Optional[str]]) -> "LangText":
        return LangText(data["t"], data["l"], original=data["o"])

    @classmethod
    def pick(cls, texts: Iterable["LangText"]) -> Optional["LangText"]:
        for lang in PREFFERED_LANGS:
            for lt in texts:
                if lt.lang == lang:
                    return lt
        for lt in texts:
            return lt
        return None

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
                lt = LangText(value, lang)
                if lt.text is None:
                    continue
                langs.add(lt)
        return langs

    def __hash__(self) -> int:
        return hash((self.text, self.lang, self.original))

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        return f"<LangText({self.text!r}, {self.lang!r}, {self.original!r})>"
