# This module buffers out some of the fingerprints package in anticipation of
# a future removal of the package. All of the functionality is now contained in
# rigour, but the different functioning of both could lead to unexpected results.
# This module is a temporary solution to allow for a smooth transition.
import logging
from collections.abc import Iterable
from functools import lru_cache

from fingerprints.cleanup import clean_name_ascii, clean_name_light
from fingerprints.types import replace_types
from normality import squash_spaces
from normality.constants import WS
from rigour.names import remove_person_prefixes

from nomenklatura.matching.util import MEMO_BATCH

log = logging.getLogger(__name__)

__all__ = [
    "clean_name_ascii",
    "clean_name_light",
    "fingerprint_name",
    "name_words",
    "names_word_list",
]


@lru_cache(maxsize=MEMO_BATCH)
def fingerprint_name(original: str) -> str | None:
    """Fingerprint a legal entity name."""
    # this needs to happen before the replacements
    text = original.lower()
    text = remove_person_prefixes(text)
    # Super hard-core string scrubbing
    cleaned = clean_name_ascii(text)
    if cleaned is None:
        return None
    cleaned = replace_types(cleaned)
    cleaned = squash_spaces(cleaned)
    if len(cleaned) < 1:
        return None
    return cleaned


def names_word_list(
    names: Iterable[str],
    min_length: int = 1,
) -> list[str]:
    """Get a list of tokens present in the given set of names."""
    words: list[str] = []
    for name in names:
        normalized = fingerprint_name(name)
        if normalized is None:
            continue
        for word in normalized.split(WS):
            if len(word) >= min_length:
                words.append(word)
    return words


def name_words(name: str | None, min_length: int = 1) -> list[str]:
    """Get a list of tokens present in the given name."""
    if name is None:
        return []
    words: list[str] = []
    for word in name.split(WS):
        if len(word) >= min_length:
            words.append(word)
    return words
