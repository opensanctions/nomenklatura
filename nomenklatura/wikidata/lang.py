import logging
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any, Optional

from followthemoney import StatementEntity, registry
from normality.cleaning import remove_unsafe_chars
from rigour.langs import MULTI_LANG, PREFERRED_LANGS

log = logging.getLogger(__name__)
PREFERRED_WD_LANGS = list(PREFERRED_LANGS)
# After English, before all the others:
PREFERRED_WD_LANGS.insert(1, MULTI_LANG)


class LangText:
    """A text value together with the language it is expressed in.

    Wikidata labels and descriptions exist in many languages. Keeping the
    language tag with the string lets `apply()` write the value to an entity
    property with the language attached, and lets callers pick a preferred
    display language. Two fields describe where a Wikidata text came from and
    are not part of the value's identity: `variant` is set when only regional
    codes (`en-us`, `pt-br`) carry it, never the language's plain code, and
    `support` counts the language slots that carry the same text, across all
    languages."""

    __slots__ = ["lang", "original", "support", "text", "variant"]

    def __init__(
        self,
        text: str | None,
        lang: str | None = None,
        original: str | None = None,
    ) -> None:
        if text is None or len(text.strip()) == 0:
            text = None
        if text is not None:
            text = remove_unsafe_chars(text)
        self.text = text
        self.lang: str | None = None
        if lang is not None:
            self.lang = registry.language.clean_text(lang)
        if lang is not None and self.lang is None:
            # Language is given, but it is not one supported by the FtM ecosystem:
            self.text = None
        self.original = original or self.text
        self.support = 1
        self.variant = False

    def apply(
        self,
        entity: StatementEntity,
        prop: str,
        clean: Callable[[str], str | None] | None = None,
    ) -> None:
        if self.text is None:
            return
        clean_text = self.text if clean is None else clean(self.text)
        if clean_text is None or clean_text.strip() == "":
            return
        entity.add(prop, clean_text, lang=self.lang, original_value=self.original)

    def pack(self) -> dict[str, str | None]:
        data = {"t": self.text, "l": self.lang}
        if self.original is not None and self.original != self.text:
            data["o"] = self.original
        return data

    @classmethod
    def parse(cls, data: dict[str, str | None]) -> "LangText":
        return LangText(data["t"], data["l"], original=data.get("o"))

    @classmethod
    def pick(cls, texts: Iterable["LangText"]) -> Optional["LangText"]:
        """Pick the display text in the first preferred language that has one,
        following Wikidata's own fallback: the language's plain-code text, then
        the `mul` text, then its regional variants.

        `mul` comes in for every language because Wikidata editors drop the
        per-language labels that repeat it, which can leave a stray `en-us`
        as the only English label. Within a tier, the text more language slots
        agree on wins, then lexicographic order, so the pick never depends on
        the iteration order of `texts`."""

        def rank(lt: LangText) -> tuple[int, int, str]:
            tier = 1 if lt.lang == MULTI_LANG else (2 if lt.variant else 0)
            return (tier, -lt.support, lt.text or "")

        texts = list(texts)
        multi = [lt for lt in texts if lt.lang == MULTI_LANG]
        for lang in PREFERRED_WD_LANGS:
            candidates = [lt for lt in texts if lt.lang == lang]
            if len(candidates) == 0:
                continue
            if lang != MULTI_LANG:
                candidates.extend(multi)
            return min(candidates, key=rank)
        if len(texts) == 0:
            return None
        return min(texts, key=lambda lt: (rank(lt), lt.lang or ""))

    @classmethod
    def sorted(cls, texts: Iterable["LangText"]) -> list["LangText"]:
        def sort_key(lt: LangText) -> Any:
            if lt.lang is None or lt.lang not in PREFERRED_WD_LANGS:
                index = len(PREFERRED_WD_LANGS)
            else:
                index = PREFERRED_WD_LANGS.index(lt.lang) + 1
            return (index, lt.text or "")

        return sorted(texts, key=sort_key)

    @classmethod
    def from_dict(cls, data: dict[str, list[dict[str, str]]]) -> set["LangText"]:
        langs: dict[LangText, LangText] = {}
        support: Counter[str] = Counter()
        for objs in data.values():
            if not isinstance(objs, list):
                objs = [objs]
            for obj in objs:
                value = obj["value"]
                if value is None:
                    continue
                support[value] += 1
                lang = obj["language"]
                lt = LangText(value, lang, original=value)
                if lt.text is None:
                    continue
                variant = "-" in lang
                existing = langs.get(lt)
                if existing is None:
                    lt.variant = variant
                    langs[lt] = lt
                else:
                    existing.variant = existing.variant and variant
        for lt in langs:
            if lt.original is not None:
                lt.support = support[lt.original]
        return set(langs)

    def __str__(self) -> str:
        if self.text is None:
            return ""
        return self.text

    def __hash__(self) -> int:
        return hash((self.text, self.lang, self.original))

    def __eq__(self, other: object) -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        return f"<LangText({self.text!r}, {self.lang!r}, {self.original!r})>"
