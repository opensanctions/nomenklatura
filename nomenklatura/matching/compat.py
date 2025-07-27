import re
import sys
import logging
from typing import Dict, Iterable, List, Optional
from functools import cache, lru_cache
from normality import squash_spaces, ascii_text, category_replace
from normality.constants import WS
from rigour.text.dictionary import Replacer
from rigour.names import remove_person_prefixes

log = logging.getLogger(__name__)

CHARACTERS_REMOVE_RE = re.compile(r"[\.\'’]")


@lru_cache(maxsize=2000)
def clean_name_ascii(text: Optional[str]) -> Optional[str]:
    """Super-hardcore string scrubbing."""
    # transliterate to ascii
    if text is None:
        return None
    text = text.lower()
    text = ascii_text(text)
    # replace punctuation and symbols
    text = CHARACTERS_REMOVE_RE.sub("", text)
    text = category_replace(text)
    text = squash_spaces(text)
    if len(text) < 2:
        return None
    return text


@cache
def _org_replacer() -> Replacer:
    """Get a replacer for the names of organization types, mapping them to generic types like LLC, JSC."""
    from rigour.data.names.org_types import ORG_TYPES
    from rigour.data.names.data import ORG_SYMBOLS

    mapping: Dict[str, str] = {}
    for org_type in ORG_TYPES:
        display_norm = clean_name_ascii(org_type.get("display"))
        generic_norm = clean_name_ascii(org_type.get("generic"))
        norm_key = generic_norm or display_norm
        if norm_key is None:
            continue
        norm_key = sys.intern(norm_key)
        if display_norm is not None:
            mapping[display_norm] = norm_key

        for alias in org_type.get("aliases", []):
            alias_norm = clean_name_ascii(alias)
            if alias_norm is None:
                continue
            # if alias_norm in mapping and mapping[alias_norm] != generic_norm:
            #     continue
            mapping[alias_norm] = norm_key

    for symbol, values in ORG_SYMBOLS.items():
        symbol = sys.intern(symbol)
        for value in values:
            value_norm = clean_name_ascii(value)
            if value_norm is None:
                continue
            mapping[value_norm] = symbol

    return Replacer(mapping, ignore_case=True)


@lru_cache(maxsize=2000)
def clean_name_light(text: str) -> Optional[str]:
    """Clean up a name for comparison, but don't convert to ASCII/Latin."""
    # replace punctuation and symbols
    text = CHARACTERS_REMOVE_RE.sub("", text)
    text = text.lower()
    cleaned = category_replace(text)
    cleaned = squash_spaces(cleaned)
    if len(cleaned) < 2:
        return None
    return cleaned


@lru_cache(maxsize=1024)
def fingerprint_name(original: str) -> Optional[str]:
    """Fingerprint a legal entity name."""
    # this needs to happen before the replacements
    text = remove_person_prefixes(original)
    # Super hard-core string scrubbing
    cleaned = clean_name_ascii(text)
    if cleaned is None:
        return text
    replaced = _org_replacer()(cleaned)
    if replaced is None:
        return None
    replaced = squash_spaces(replaced)
    if len(replaced) < 2:
        return None
    return replaced


def names_word_list(
    names: Iterable[str],
    min_length: int = 1,
) -> List[str]:
    """Get a list of tokens present in the given set of names."""
    words: List[str] = []
    for name in names:
        normalized = fingerprint_name(name)
        if normalized is None:
            continue
        for word in normalized.split(WS):
            if len(word) >= min_length:
                words.append(word)
    return words


def name_words(name: Optional[str], min_length: int = 1) -> List[str]:
    """Get a list of tokens present in the given name."""
    if name is None:
        return []
    words: List[str] = []
    for word in name.split(WS):
        if len(word) >= min_length:
            words.append(word)
    return words
