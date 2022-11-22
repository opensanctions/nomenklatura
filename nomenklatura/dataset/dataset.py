from typing import Any, Dict, TypeVar

DS = TypeVar("DS", bound="Dataset")


class Dataset(object):
    """A unit of entities. A dataset is a set of data, sez W3C."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self.title = title

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "title": self.title}

    def __eq__(self, other: Any) -> bool:
        try:
            return not not self.name == other.name
        except AttributeError:
            return False

    def __lt__(self, other: "Dataset") -> bool:
        return self.name.__lt__(other.name)

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self.name))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name!r})>"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dataset":
        return cls(name=data["name"], title=data["title"])


DatasetIndex = Dict[str, Dataset]
