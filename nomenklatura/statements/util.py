from datetime import datetime
from typing import Optional


CSV_COLUMNS = [
    "canonical_id",
    "entity_id",
    "prop",
    "prop_type",
    "schema",
    "value",
    "dataset",
    "target",
    "external",
    "first_seen",
    "last_seen",
    "id",
]


def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string"""
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def datetime_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")
