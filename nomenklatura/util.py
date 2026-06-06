import re
import os
from pathlib import Path
from collections.abc import Mapping
from typing import Iterable, TypeVar, List, Union, Optional

T = TypeVar("T")
DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
HeadersType = Optional[Mapping[str, Union[str, bytes, None]]]


def unroll(values: Iterable[Iterable[T]]) -> List[T]:
    unrolled: List[T] = []
    for sub in values:
        unrolled.extend(sub)
    return unrolled
