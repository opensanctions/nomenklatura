from typing import Optional, List, Any, Dict
from followthemoney.types import registry

from nomenklatura.dataset.util import type_check, type_require, cleanup


class DataCoverage(object):
    """Details on the temporal and geographic scope of a dataset."""

    def __init__(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        countries: List[str] = [],
    ):
        self.start = start
        self.end = end
        self.countries = countries

    def to_dict(self) -> Dict[str, Any]:
        data = {"start": self.start, "end": self.end, "countries": self.countries}
        return cleanup(data)

    def __repr__(self) -> str:
        return f"<DataCoverage({self.start!r}>{self.end!r}, {self.countries!r})>"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataCoverage":
        countries: List[str] = []
        for country in data.get("countries", []):
            countries.append(type_require(registry.country, country))
        return cls(
            start=type_check(registry.date, data.get("start")),
            end=type_check(registry.date, data.get("end")),
            countries=countries,
        )
