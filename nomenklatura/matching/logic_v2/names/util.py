from typing import Optional
from rigour.names import tokenize_name, prenormalize_name


def normalize_name(name: Optional[str]) -> str:
    """Normalize a name for tokenization and matching."""
    norm = prenormalize_name(name)
    return " ".join(tokenize_name(norm))


def name_normalizer(name: Optional[str]) -> Optional[str]:
    """Same as before, but meeting the definition of a rigour Normalizer."""
    if name is None:
        return None
    name = normalize_name(name)
    if len(name) == 0:
        return None
    return name
