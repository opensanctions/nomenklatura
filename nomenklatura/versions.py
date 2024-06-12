import os
import json
import string
import random
from typing import Any, List, Iterator, Optional
from datetime import datetime, timezone

ALPHABET = string.ascii_lowercase


class Version(object):
    """A class to represent a dataset version, which consists of a timestamp
    and a string tag."""

    __slots__ = ["dt", "tag"]

    def __init__(self, dt: datetime, tag: str) -> None:
        self.dt: datetime = dt
        self.tag: str = tag

    @classmethod
    def new(cls, tag: Optional[str] = None) -> "Version":
        now = datetime.now().astimezone(timezone.utc)
        now = now.replace(tzinfo=None)

        if tag is None:
            # This keeps the tag sortable but short.
            tag_num = (now.microsecond // 1000) * 10
            tag_num_ = tag_num + random.randint(0, 9)
            tag = cls._tag_encode(int(tag_num_))

        tag = tag.ljust(3, "x")[:3]
        now = now.replace(microsecond=0)
        return cls(now, tag)

    @classmethod
    def from_string(cls, id: str) -> "Version":
        if "-" not in id:
            raise ValueError(f"Invalid dataset version: {id}")
        ts, tag = id.split("-", 1)
        dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
        dt = dt.replace(tzinfo=None)
        return cls(dt, tag)

    @classmethod
    def _tag_encode(cls, number: int, alphabet: str = ALPHABET) -> str:
        """Converts an integer to a base36 string."""
        assert number >= 0, "number must be positive"
        if 0 <= number < len(alphabet):
            return alphabet[number]

        encoded = ""
        while number != 0:
            number, i = divmod(number, len(alphabet))
            encoded = alphabet[i] + encoded
        return encoded

    @classmethod
    def from_env(cls, name: str) -> "Version":
        id = os.environ.get(name)
        if id is None:
            return cls.new()
        return cls.from_string(id)

    @property
    def id(self) -> str:
        return f"{self.dt.strftime('%Y%m%d%H%M%S')}-{self.tag}"

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return f"Version({self.id})"

    def __eq__(self, other: Any) -> bool:
        return self.id == str(other)

    def __hash__(self) -> int:
        return hash(self.id)


class VersionHistory(object):
    """A class to represent a history of dataset versions."""

    LENGTH = 100

    def __init__(self, items: List[Version], max_length: int = LENGTH) -> None:
        self.items = items
        self.max_length = max_length

    def append(self, version: Version) -> "VersionHistory":
        """Creates a new history with the given RunID appended."""
        items = list(self.items)
        items.append(version)
        return VersionHistory(items[-self.max_length :])

    @property
    def latest(self) -> Optional[Version]:
        if not len(self.items):
            return None
        return self.items[-1]

    def to_json(self) -> str:
        """Return a JSON representation of the version history."""
        items = [str(run) for run in self.items[-self.LENGTH :]]
        return json.dumps({"items": items})

    @classmethod
    def from_json(cls, data: str) -> "VersionHistory":
        """Create a run history from a JSON representation."""
        items = json.loads(data).get("items", [])
        items = [Version.from_string(item) for item in items]
        return cls(items)

    def __iter__(self) -> Iterator[Version]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)
