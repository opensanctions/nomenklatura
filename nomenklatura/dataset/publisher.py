from banal import as_bool
from typing import Optional, Dict, Any
from followthemoney.types import registry

from nomenklatura.dataset.util import Named, cleanup
from nomenklatura.dataset.util import type_check, type_require


class DataPublisher(Named):
    """Publisher information, eg. the government authority."""

    def __init__(
        self,
        name: str,
        url: str,
        description: Optional[str] = None,
        country: Optional[str] = None,
        official: bool = False,
    ):
        super().__init__(name)
        self.url = url
        self.description = description
        self.country = country
        self.official = official

    @property
    def country_label(self) -> Optional[str]:
        if self.country is None:
            return None
        return registry.country.caption(self.country)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "country": self.country,
            "country_label": self.country_label,
            "official": self.official,
        }
        return cleanup(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataPublisher":
        return cls(
            name=type_require(registry.string, data.get("name")),
            url=type_require(registry.url, data.get("url")),
            description=type_check(registry.string, data.get("description")),
            country=type_check(registry.country, data.get("country")),
            official=as_bool(data.get("official", False)),
        )
