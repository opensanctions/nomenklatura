import re
import logging
from typing import Iterable, List, Optional
from functools import lru_cache
from normality import squash_spaces, ascii_text, category_replace
from normality.constants import WS
from rigour.names import remove_person_prefixes
from rigour.names.org_types import replace_org_types_compare

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
    replaced = replace_org_types_compare(
        cleaned, normalizer=clean_name_ascii, generic=True
    )
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
