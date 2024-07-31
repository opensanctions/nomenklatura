import re
import os
from pathlib import Path
from datetime import datetime, timezone
from followthemoney import model
from functools import lru_cache, cache
from normality import collapse_spaces, category_replace
from normality.constants import WS
from rigour.text import metaphone, soundex
from collections.abc import Mapping, Sequence
from fingerprints.cleanup import clean_name_ascii, clean_entity_prefix
from fingerprints.cleanup import CHARACTERS_REMOVE_RE
from fingerprints import replace_types
from followthemoney.util import sanitize_text
from typing import cast, Any, Union, Iterable, Tuple, Optional, List, Callable

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
BASE_ID = "id"
PathLike = Union[str, os.PathLike[str]]
HeadersType = Optional[Mapping[str, Union[str, bytes, None]]]


def string_list(value: Any) -> List[str]:
    """Convert a value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        text = sanitize_text(value)
        if text is None:
            return []
        return [text]
    if not isinstance(value, (Sequence, set)):
        value = [value]
    texts: List[str] = []
    for inner in value:
        if isinstance(inner, Mapping):
            text = inner.get("id")
            if text is not None:
                texts.append(text)
            continue

        try:
            texts.append(inner.id)
            continue
        except AttributeError:
            pass

        text = sanitize_text(inner)
        if text is not None:
            texts.append(text)

    return texts


@lru_cache(maxsize=1000)
def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string"""
    if value is None or len(value) == 0:
        return None
    value = value[:19].replace(" ", "T")
    dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def datetime_iso(dt: Optional[Union[str, datetime]]) -> Optional[str]:
    if dt is None:
        return dt
    try:
        return dt.isoformat(sep="T", timespec="seconds")  # type: ignore
    except AttributeError:
        return cast(str, dt)


def iso_to_version(value: str) -> Optional[str]:
    dt = iso_datetime(value)
    if dt is not None:
        return dt.strftime("%Y%m%d%H%M%S")
    return None


def bool_text(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "t" if value else "f"


@cache
def text_bool(text: Optional[str]) -> Optional[bool]:
    if text is None or len(text) == 0:
        return None
    return text.lower().startswith("t")


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


def phonetic_token(token: str) -> str:
    return metaphone_token(token)


def metaphone_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        out = metaphone(token)
        # doesn't handle non-ascii characters
        if len(out) >= 3:
            return out
    return token.upper()


def soundex_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        out = soundex(token)
        # doesn't handle non-ascii characters
        if len(out):
            return out
    return token.upper()


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


def pack_prop(schema: str, prop: str) -> str:
    return f"{schema}:{prop}"


@cache
def get_prop_type(schema: str, prop: str) -> str:
    if prop == BASE_ID:
        return BASE_ID
    schema_obj = model.get(schema)
    if schema_obj is None:
        raise TypeError("Schema not found: %s" % schema)
    prop_obj = schema_obj.get(prop)
    if prop_obj is None:
        raise TypeError("Property not found: %s" % prop)
    return prop_obj.type.name


@cache
def unpack_prop(id: str) -> Tuple[str, str, str]:
    schema, prop = id.split(":", 1)
    prop_type = get_prop_type(schema, prop)
    return schema, prop_type, prop
