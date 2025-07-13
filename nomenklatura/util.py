import re
import os
from pathlib import Path
from functools import lru_cache
from normality import collapse_spaces, category_replace
from normality.constants import WS
from collections.abc import Mapping
from fingerprints.cleanup import clean_name_ascii, clean_entity_prefix
from fingerprints.cleanup import CHARACTERS_REMOVE_RE
from fingerprints import replace_types
from rigour.time import iso_datetime
from typing import Union, Iterable, Optional, List, Callable

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
HeadersType = Optional[Mapping[str, Union[str, bytes, None]]]


def iso_to_version(value: str) -> Optional[str]:
    ## Phase this out - it won't be used in new FtM metadata, is used by yente
    dt = iso_datetime(value)
    if dt is not None:
        return dt.strftime("%Y%m%d%H%M%S")
    return None


@lru_cache(maxsize=1024)
def fingerprint_name(original: str) -> Optional[str]:
    """Fingerprint a legal entity name."""
    # this needs to happen before the replacements
    text = original.lower()
    text = clean_entity_prefix(text)
    # Super hard-core string scrubbing
    cleaned = clean_name_ascii(text)
    cleaned = replace_types(cleaned)
    return collapse_spaces(cleaned)


def clean_text_basic(text: Optional[str]) -> Optional[str]:
    """Clean up some text for comparison and tokenization, do not transliterate."""
    if text is None:
        return None
    text = CHARACTERS_REMOVE_RE.sub("", text)
    text = text.lower()
    return category_replace(text)


def name_words(name: Optional[str], min_length: int = 1) -> List[str]:
    """Get a list of tokens present in the given name."""
    if name is None:
        return []
    words: List[str] = []
    for word in name.split(WS):
        if len(word) >= min_length:
            words.append(word)
    return words


def names_word_list(
    names: Iterable[str],
    normalizer: Callable[[str], Optional[str]] = fingerprint_name,
    processor: Optional[Callable[[str], str]] = None,
    min_length: int = 1,
) -> List[str]:
    """Get a list of tokens present in the given set of names."""
    words: List[str] = []
    for name in names:
        normalized = normalizer(name)
        for word in name_words(normalized, min_length=min_length):
            if processor is not None:
                word = processor(word)
            words.append(word)
    return words


def normalize_name(original: str) -> Optional[str]:
    """Normalize a legal entity name."""
    return clean_name_ascii(original)


def list_intersection(left: List[str], right: List[str]) -> int:
    """Return the number of elements in the intersection of two lists, accounting
    properly for duplicates."""
    overlap = 0
    remainder = list(right)
    for elem in left:
        try:
            remainder.remove(elem)
            overlap += 1
        except ValueError:
            pass
    return overlap
