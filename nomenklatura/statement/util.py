from datetime import datetime
from typing import Optional


def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string"""
    if value is None or len(value) == 0:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def datetime_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def bool_text(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "true" if value else "false"


def text_bool(text: Optional[str]) -> Optional[bool]:
    if text is None or len(text) == 0:
        return None
    return text.lower().startswith("t")
