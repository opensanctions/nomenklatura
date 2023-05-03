from typing import Any, Dict, Iterable, List, Optional

from followthemoney.types import registry
from followthemoney.types.common import PropertyType
from normality import stringify

from nomenklatura.exceptions import MetadataException


def type_check(
    type_: PropertyType, value: Any, options: Iterable[str] = []
) -> Optional[str]:
    text = stringify(value)
    if text is None:
        return None
    cleaned = type_.clean_text(text)
    if cleaned is None:
        raise MetadataException("Invalid %s: %r" % (type_.name, value))
    if options and cleaned not in options:
        raise MetadataException(
            "Invalid %s: %r not in %s" % (type_.name, value, ",".join(options))
        )
    return cleaned


def type_require(type_: PropertyType, value: Any) -> str:
    text = stringify(value)
    if text is None:
        raise MetadataException("Invalid %s: %r" % (type_.name, value))
    cleaned = type_.clean_text(text)
    if cleaned is None:
        raise MetadataException("Invalid %s: %r" % (type_.name, value))
    return cleaned


def string_list(value: Any) -> List[str]:
    if value is None:
        return []
    return [type_require(registry.string, s) for s in value]


def cleanup(data: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in list(data.items()):
        if value is None:
            data.pop(key)
    return data


class Named(object):
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: Any) -> bool:
        try:
            return not not self.name == other.name
        except AttributeError:
            return False

    def __lt__(self, other: Any) -> bool:
        return self.name.__lt__(other.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name!r})>"
