from typing import Dict, Any, Optional, Set, List
from rigour.names import pick_name
from followthemoney.model import Model
from followthemoney.proxy import EntityProxy


def _defined(*args: Optional[str]) -> List[str]:
    return [arg for arg in args if arg is not None]


class StreamEntity(EntityProxy):
    """This is used to retain extra attributes in the entity when doing streaming
    command-line operations where the statement data is not available."""

    def __init__(
        self,
        model: Model,
        data: Dict[str, Any],
        key_prefix: Optional[str] = None,
        cleaned: bool = True,
    ):
        super().__init__(model, data, key_prefix=key_prefix, cleaned=cleaned)
        self._caption: Optional[str] = data.get("caption")
        self.datasets: Set[str] = set(data.get("datasets", []))
        self.referents: Set[str] = set(data.get("referents", []))
        self.first_seen: Optional[str] = data.get("first_seen")
        self.last_seen: Optional[str] = data.get("last_seen")
        self.last_change: Optional[str] = data.get("last_change")
        self.target: Optional[bool] = data.get("target", False)
        self.context = {}

    def merge(self: "StreamEntity", other: "StreamEntity") -> "StreamEntity":
        merged = super().merge(other)
        merged._caption = pick_name(_defined(self._caption, other._caption))
        merged.referents.update(other.referents)
        merged.datasets.update(other.datasets)
        self.first_seen = min(_defined(self.first_seen, other.first_seen), default=None)
        self.last_seen = max(_defined(self.last_seen, other.last_seen), default=None)
        self.target = self.target or other.target
        changed = _defined(self.last_change, other.last_change)
        self.last_change = max(changed, default=None)
        return merged

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "caption": self._caption or self.caption,
            "schema": self.schema.name,
            "properties": self.properties,
            "referents": list(self.referents),
            "datasets": list(self.datasets),
            "target": self.target,
        }
        if self.first_seen is not None:
            data["first_seen"] = self.first_seen
        if self.last_seen is not None:
            data["last_seen"] = self.last_seen
        if self.last_change is not None:
            data["last_change"] = self.last_change
        return data
