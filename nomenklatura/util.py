import re
import os
from pathlib import Path
from datetime import datetime
from functools import lru_cache
from normality.constants import WS
from fingerprints.fingerprint import fingerprint
from fingerprints.cleanup import clean_strict
from typing import Any, Mapping, Union, Iterable, Tuple, Optional, List, Set
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
QID = re.compile(r"^Q(\d+)$")
PathLike = Union[str, os.PathLike[str]]
ParamsType = Union[None, Iterable[Tuple[str, Any]], Mapping[str, Any]]


def is_qid(text: Optional[str]) -> bool:
    """Determine if the given string is a valid wikidata QID."""
    if text is None:
        return False
    return QID.match(text) is not None


def normalize_url(url: str, params: ParamsType = None) -> str:
    """Compose a URL with the given query parameters."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if params is not None:
        values = params.items() if isinstance(params, Mapping) else params
        query.extend(sorted(values))
    parsed = parsed._replace(query=urlencode(query))
    return urlunparse(parsed)


def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string"""
    if value is None or len(value) == 0:
        return None
    value = value[:19].replace("T", " ")
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def datetime_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def iso_to_version(value: str) -> Optional[str]:
    dt = iso_datetime(value)
    if dt is not None:
        return dt.strftime("%Y%m%d%H%M%S")
    return None


def bool_text(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "true" if value else "false"


def text_bool(text: Optional[str]) -> Optional[bool]:
    if text is None or len(text) == 0:
        return None
    return text.lower().startswith("t")


@lru_cache(maxsize=10000)
def fingerprint_name(original: str, keep_order: bool = True) -> Optional[str]:
    """Fingerprint a legal entity name."""
    return fingerprint(original, keep_order=keep_order)


def name_words(names: List[str]) -> Set[str]:
    """Get a unique set of tokens present in the given set of names."""
    words: Set[str] = set()
    for name in names:
        normalized = fingerprint_name(name)
        if normalized is not None:
            words.update(normalized.split(WS))
    return words


@lru_cache(maxsize=10000)
def normalize_name(original: str) -> Optional[str]:
    """Normalize a legal entity name."""
    return clean_strict(original)
