from dataclasses import dataclass
from typing import List, Optional, Tuple
from normality import squash_spaces
from prefixdate import parse, Precision

# QuickStatements time precision integers, as used in the `/precision` suffix of
# a time value. They differ from prefixdate's `Precision` (which counts string
# length), so we map between the two explicitly.
# cf. https://www.wikidata.org/wiki/Help:Dates#Precision
WD_PRECISION_YEAR = 9
WD_PRECISION_MONTH = 10
WD_PRECISION_DAY = 11

# Reference snak properties shared across emitted statements.
REF_URL = "S854"  # reference URL
REF_RETRIEVED = "S813"  # retrieved-at date


class QSValue:
    """A typed Wikidata value that knows how to render itself as a QuickStatements token.

    Use the constructors (`item`, `string`, `monolingual`, `date`) rather than
    instantiating subclasses directly; they pick the right value type and handle
    the awkward cases (date precision, missing input) in one place. `render()`
    produces the bare token that goes into a tab-separated QuickStatements column.
    """

    def render(self) -> str:
        raise NotImplementedError

    @classmethod
    def item(cls, qid: str) -> "ItemValue":
        return ItemValue(qid)

    @classmethod
    def string(cls, text: str) -> "StringValue":
        return StringValue(text)

    @classmethod
    def monolingual(cls, lang: str, text: str) -> "MonolingualValue":
        return MonolingualValue(lang, text)

    @classmethod
    def date(cls, value: str) -> Optional["TimeValue"]:
        """Build a time value from a date string, deriving QS precision from it.

        Returns ``None`` when the string holds no usable date, so callers can skip
        the statement instead of emitting a malformed token. A bare year yields
        year precision, ``YYYY-MM`` month precision, and a full date day precision.
        """
        prefix = parse(value)
        if prefix.text is None:
            return None
        return _time_from_prefix(prefix.text, prefix.precision)


def _time_from_prefix(text: str, precision: Precision) -> Optional["TimeValue"]:
    if precision.value >= Precision.DAY.value:
        return TimeValue(text[:10], WD_PRECISION_DAY)
    if precision == Precision.MONTH:
        return TimeValue(text[:7], WD_PRECISION_MONTH)
    if precision == Precision.YEAR:
        return TimeValue(text[:4], WD_PRECISION_YEAR)
    return None


def _escape(text: str) -> str:
    """Escape a string for use inside a double-quoted QuickStatements value."""
    # squash_spaces collapses any whitespace runs (incl. tabs/newlines, which
    # would otherwise break the tab-separated line) into single spaces and trims.
    text = squash_spaces(text)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    return text


@dataclass(frozen=True)
class ItemValue(QSValue):
    qid: str

    def render(self) -> str:
        return self.qid


@dataclass(frozen=True)
class StringValue(QSValue):
    text: str

    def render(self) -> str:
        return f'"{_escape(self.text)}"'


@dataclass(frozen=True)
class MonolingualValue(QSValue):
    lang: str
    text: str

    def render(self) -> str:
        return f'{self.lang}:"{_escape(self.text)}"'


@dataclass(frozen=True)
class TimeValue(QSValue):
    """A date value rendered as ``+YYYY-MM-DDT00:00:00Z/precision``.

    The stored ``text`` is a date prefix (year, year-month or full date); the
    rendered token always pads to a full timestamp at midnight UTC and carries
    the QS precision integer (9=year, 10=month, 11=day).
    """

    text: str
    precision: int

    def render(self) -> str:
        parts = self.text.split("-")
        year = parts[0]
        month = parts[1] if len(parts) > 1 else "01"
        day = parts[2] if len(parts) > 2 else "01"
        stamp = f"+{year}-{month}-{day}T00:00:00Z"
        return f"{stamp}/{self.precision}"


Snak = Tuple[str, QSValue]


def url_reference(url: str, retrieved: Optional[str] = None) -> List[Snak]:
    """Build the standard reference snaks for a sourced statement.

    Reach for this when emitting a statement derived from an OpenSanctions
    source: it pairs the source URL (``S854``) with an optional retrieved-at
    date (``S813``), the citation shape Wikidata expects for automated edits.
    """
    snaks: List[Snak] = [(REF_URL, QSValue.string(url))]
    if retrieved is not None:
        date = QSValue.date(retrieved)
        if date is not None:
            snaks.append((REF_RETRIEVED, date))
    return snaks
