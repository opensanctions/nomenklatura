from normality import stringify
from typing import Any, List, Tuple


def join_text(*parts: Any, sep: str = " ") -> str:
    """Join all the non-null arguments using sep."""
    texts: List[str] = []
    for part in parts:
        text = stringify(part)
        if text is not None:
            texts.append(text)
    return sep.join(texts)
