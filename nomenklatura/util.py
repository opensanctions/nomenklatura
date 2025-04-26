import re
import os
from pathlib import Path
from datetime import datetime, timezone
from followthemoney import model
from functools import lru_cache, cache
from collections.abc import Mapping, Sequence
from followthemoney.util import sanitize_text
from typing import cast, Any, Union, Tuple, Optional, List

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
BASE_ID = "id"
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
    ## Phase this out - it won't be used in new FtM metadata, is used by yente
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
