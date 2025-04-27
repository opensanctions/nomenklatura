import unicodedata
from rigour.names import tokenize_name


def prenormalize_name(name: str) -> str:
    """Prepare a name for tokenization and matching."""
    name = unicodedata.normalize("NFC", name)
    return name.lower()


def normalize_name(name: str) -> str:
    """Normalize a name for tokenization and matching."""
    name = prenormalize_name(name)
    return " ".join(tokenize_name(name))
