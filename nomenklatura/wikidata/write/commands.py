from dataclasses import dataclass, field
from typing import List

from nomenklatura.wikidata.write.values import QSValue, Snak

# Sentinel target meaning "the most recently CREATEd item" — rendered as the
# literal `LAST` keyword. Statements about a freshly created item reference it
# this way because QuickStatements assigns its QID asynchronously.
LAST = "LAST"

# A statement/label/etc. target: either an explicit QID or the LAST sentinel.
Target = str


class QSCommand:
    """A single QuickStatements command, the unit a batch is built from.

    These are plain data carriers; rendering to V1 text lives in
    `serialize.py`. Compose a `list[QSCommand]` (typically one `CreateItem`
    followed by labels and `AddStatement`s targeting `LAST`, or `AddStatement`s
    targeting an existing QID when enriching) and hand it to the serializer.
    """


@dataclass
class CreateItem(QSCommand):
    """Create a new item; subsequent commands target it via the `LAST` sentinel."""


@dataclass
class SetLabel(QSCommand):
    target: Target
    lang: str
    text: str


@dataclass
class SetDescription(QSCommand):
    target: Target
    lang: str
    text: str


@dataclass
class SetAlias(QSCommand):
    target: Target
    lang: str
    text: str


@dataclass
class AddStatement(QSCommand):
    """Add a property value to an item, optionally qualified and sourced.

    `target` is a QID or `LAST`; `prop` is a property id like ``"P569"``.
    Qualifiers append as trailing property columns; references append as the
    same value formatting under `S`-prefixed columns. QuickStatements de-dups
    against existing statements, so emitting one that already exists is a no-op.
    """

    target: Target
    prop: str
    value: QSValue
    qualifiers: List[Snak] = field(default_factory=list)
    references: List[Snak] = field(default_factory=list)
