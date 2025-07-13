import re
import os
from pathlib import Path
from collections.abc import Mapping
from typing import Union, Optional
from rigour.time import iso_datetime

DATA_PATH = Path(os.path.join(os.path.dirname(__file__), "data")).resolve()
ID_CLEAN = re.compile(r"[^A-Z0-9]+", re.UNICODE)
HeadersType = Optional[Mapping[str, Union[str, bytes, None]]]


def iso_to_version(value: str) -> Optional[str]:
    ## Phase this out - it won't be used in new FtM metadata, is used by yente
    dt = iso_datetime(value)
    if dt is not None:
        return dt.strftime("%Y%m%d%H%M%S")
    return None
