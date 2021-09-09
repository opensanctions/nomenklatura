from typing import Any


class Dataset(object):
    """A unit of entities. A dataset is a set of data, sez W3C."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self.title = title

    def __eq__(self, other: Any) -> bool:
        try:
            return not not self.name == other.name
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self.name))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name!r})>"
