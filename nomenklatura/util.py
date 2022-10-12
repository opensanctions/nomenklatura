import re
import os
from pathlib import Path
from typing import Any, Mapping, Union, Iterable, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
QID = re.compile(r"^Q(\d+)$")
PathLike = Union[str, os.PathLike[str]]
ParamsType = Union[None, Iterable[Tuple[str, Any]], Mapping[str, Any]]


def is_qid(text: str) -> bool:
    """Determine if the given string is a valid wikidata QID."""
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
