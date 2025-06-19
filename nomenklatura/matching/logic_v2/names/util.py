from typing import Optional
import unicodedata
from rigour.names import tokenize_name
from rigour.text import levenshtein


def strict_levenshtein(left: str, right: str, max_rate: int = 4) -> float:
    """Calculate the string distance between two strings."""
    if left == right:
        return 1.0
    max_len = max(len(left), len(right))
    max_edits = max_len // max_rate
    if max_edits < 1:  # We already checked for equality
        return 0.0
    distance = levenshtein(left, right, max_edits=max_len)
    if distance > max_edits:
        return 0.0
    return (1 - (distance / max_len)) ** max_edits


def prenormalize_name(name: str) -> str:
    """Prepare a name for tokenization and matching."""
    name = unicodedata.normalize("NFC", name)
    return name.lower()


def name_prenormalizer(name: Optional[str]) -> Optional[str]:
    """Same as before, but meeting the definition of a rigour Normalizer."""
    if name is None:
        return None
    name = prenormalize_name(name)
    if len(name) == 0:
        return None
    return name


def normalize_name(name: str) -> str:
    """Normalize a name for tokenization and matching."""
    name = prenormalize_name(name)
    return " ".join(tokenize_name(name))


def name_normalizer(name: Optional[str]) -> Optional[str]:
    """Same as before, but meeting the definition of a rigour Normalizer."""
    if name is None:
        return None
    name = normalize_name(name)
    if len(name) == 0:
        return None
    return name
