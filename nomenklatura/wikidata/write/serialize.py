from typing import Iterable, List

from nomenklatura.wikidata.write.commands import (
    QSCommand,
    CreateItem,
    SetLabel,
    SetDescription,
    SetAlias,
    AddStatement,
)
from nomenklatura.wikidata.write.values import StringValue

TAB = "\t"


def _line(*columns: str) -> str:
    return TAB.join(columns)


def serialize_command(command: QSCommand) -> str:
    """Render a single command to its QuickStatements V1 line."""
    if isinstance(command, CreateItem):
        return "CREATE"
    if isinstance(command, SetLabel):
        return _line(command.target, f"L{command.lang}", _quote(command.text))
    if isinstance(command, SetDescription):
        return _line(command.target, f"D{command.lang}", _quote(command.text))
    if isinstance(command, SetAlias):
        return _line(command.target, f"A{command.lang}", _quote(command.text))
    if isinstance(command, AddStatement):
        columns: List[str] = [command.target, command.prop, command.value.render()]
        for prop, value in command.qualifiers:
            columns.extend([prop, value.render()])
        for prop, value in command.references:
            columns.extend([prop, value.render()])
        return _line(*columns)
    raise TypeError(f"Unknown command: {command!r}")


def serialize(commands: Iterable[QSCommand]) -> str:
    """Render a command list to QuickStatements V1 text, one command per line.

    This is the terminal step of the write module: feed it the commands built
    for an enrich or create batch and write the result to a ``.qs`` file the
    operator runs in the QuickStatements web UI. The output has no trailing
    newline; join multiple batches yourself if needed.
    """
    return "\n".join(serialize_command(c) for c in commands)


def _quote(text: str) -> str:
    """Escape and double-quote a label/description/alias string value."""
    return StringValue(text).render()
