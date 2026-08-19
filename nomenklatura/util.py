import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")
DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
HeadersType = Mapping[str, str | bytes | None] | None


def unroll(values: Iterable[Iterable[T]]) -> list[T]:
    unrolled: list[T] = []
    for sub in values:
        unrolled.extend(sub)
    return unrolled
