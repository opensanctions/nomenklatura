from normality import stringify
from typing import Any, List, Tuple


def join_text(*parts: Tuple[Any], sep=" ") -> str:
    """Join all the non-null arguments using sep."""
    texts: List[str] = []
    for part in parts:
        text = stringify(part)
        if text is not None:
            texts.append(text)
    return sep.join(texts)
