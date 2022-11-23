from typing import Optional, Dict, Any
from followthemoney.types import registry

from nomenklatura.dataset.util import Named, cleanup
from nomenklatura.dataset.util import type_check, type_require


class DataResource(Named):
    """A downloadable resource that is part of a dataset."""

    def __init__(
        self,
        name: str,
        url: str,
        checksum: Optional[str] = None,
        timestamp: Optional[str] = None,
        mime_type: Optional[str] = None,
        title: Optional[str] = None,
        size: Optional[int] = None,
    ):
        super().__init__(name)
        self.url = url
        self.checksum = checksum
        self.timestamp = timestamp
        self.mime_type = mime_type
        self.title = title
        self.size = size

    @property
    def mime_type_label(self) -> Optional[str]:
        if self.mime_type is None:
            return None
        return registry.mimetype.caption(self.mime_type)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "url": self.url,
            "checksum": self.checksum,
            "timestamp": self.timestamp,
            "mime_type": self.mime_type,
            "mime_type_label": self.mime_type_label,
            "title": self.title,
            "size": self.size,
        }
        return cleanup(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataResource":
        name = data.get("name", data.get("path"))
        size = int(data["size"]) if "size" in data else None
        return cls(
            name=type_require(registry.string, name),
            url=type_require(registry.url, data.get("url")),
            checksum=type_check(registry.checksum, data.get("checksum")),
            timestamp=type_check(registry.date, data.get("timestamp")),
            mime_type=type_check(registry.mimetype, data.get("mime_type")),
            title=type_check(registry.string, data.get("title")),
            size=size,
        )
