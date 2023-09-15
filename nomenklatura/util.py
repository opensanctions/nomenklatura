import re
import os
from pathlib import Path
from datetime import datetime
from functools import lru_cache, cache
from jellyfish import damerau_levenshtein_distance, metaphone
from jellyfish import jaro_winkler_similarity, soundex
from normality.constants import WS
from followthemoney import model
from collections.abc import Mapping, Sequence
from fingerprints.fingerprint import fingerprint
from fingerprints.cleanup import clean_strict
from followthemoney.util import sanitize_text
from typing import cast, Any, Union, Iterable, Tuple, Optional, List, Set
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
QID = re.compile(r"^Q(\d+)$")
BASE_ID = "id"
PathLike = Union[str, os.PathLike[str]]
ParamsType = Union[None, Iterable[Tuple[str, Any]], Mapping[str, Any]]


def is_qid(text: Optional[str]) -> bool:
    """Determine if the given string is a valid wikidata QID."""
    if text is None:
        return False
    return QID.match(text) is not None


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


def normalize_url(url: str, params: ParamsType = None) -> str:
    """Compose a URL with the given query parameters."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if params is not None:
        values = params.items() if isinstance(params, Mapping) else params
        query.extend(sorted(values))
    parsed = parsed._replace(query=urlencode(query))
    return urlunparse(parsed)


@lru_cache(maxsize=1000)
def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string"""
    if value is None or len(value) == 0:
        return None
    value = value[:19].replace(" ", "T")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")


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
def fingerprint_name(original: str, keep_order: bool = True) -> Optional[str]:
    """Fingerprint a legal entity name."""
    return fingerprint(original, keep_order=keep_order, keep_brackets=True)


def name_words(names: Iterable[str]) -> Set[str]:
    """Get a unique set of tokens present in the given set of names."""
    words: Set[str] = set()
    for name in names:
        normalized = fingerprint_name(name)
        if normalized is not None:
            words.update(normalized.split(WS))
    return words


@lru_cache(maxsize=1024)
def normalize_name(original: str) -> Optional[str]:
    """Normalize a legal entity name."""
    return clean_strict(original)


@lru_cache(maxsize=1024)
def phonetic_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        return metaphone(token)
    return token.upper()


@lru_cache(maxsize=1024)
def soundex_token(token: str) -> str:
    if token.isalpha() and len(token) > 1:
        return soundex(token)
    return token.upper()


@lru_cache(maxsize=1024)
def levenshtein(left: str, right: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    return damerau_levenshtein_distance(left[:128], right[:128])


@lru_cache(maxsize=1024)
def jaro_winkler(left: str, right: str) -> float:
    score = jaro_winkler_similarity(left, right)
    return score if score > 0.6 else 0.0


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
