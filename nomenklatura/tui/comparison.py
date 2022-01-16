import asyncio
from typing import TYPE_CHECKING
from normality import latinize_text
from rich.console import RenderableType  # type: ignore
from rich.table import Table  # type: ignore
from rich.text import Text  # type: ignore
from textual.widget import Widget  # type: ignore
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.loader import Loader, DS, E
from nomenklatura.tui.util import comparison_props

if TYPE_CHECKING:
    from nomenklatura.tui.app import DedupeApp


def render_column(entity: E) -> Text:
    return Text.assemble(
        (entity.schema.label, "blue"), " [%s]" % entity.id, no_wrap=True
    )


async def render_values(
    loader: Loader[DS, E], prop: Property, entity: E, other: E, latinize: bool
) -> Text:
    values = entity.get(prop, quiet=True)
    other_values = other.get_type_values(prop.type)
    text = Text()
    for i, value in enumerate(sorted(values)):
        if i > 0:
            text.append(" · ")
        caption = prop.type.caption(value)
        if prop.type == registry.entity:
            sub = loader.get_entity(value)
            if sub is not None:
                caption = sub.caption
        score = prop.type.compare_sets([value], other_values)
        if latinize:
            caption = latinize_text(caption) or caption
        style = "default"
        if score > 0.7:
            style = "yellow"
        if score > 0.95:
            style = "green"
        if caption is not None:
            text.append(caption, style)
    return text


async def render_comparison(
    loader: Loader[DS, E], left: E, right: E, score: float, latinize: bool = False
) -> Table:
    if left is None or right is None:
        return Text("No candidates loaded.", justify="center")

    table = Table(expand=True)
    score_text = "Score: %.3f" % score
    table.add_column(score_text, justify="right", no_wrap=True, ratio=2)
    table.add_column(render_column(left), ratio=5)
    table.add_column(render_column(right), ratio=5)

    for prop in comparison_props(left, right):
        label = Text(prop.label, "white bold")
        left_text = await render_values(loader, prop, left, right, latinize)
        right_text = await render_values(loader, prop, right, left, latinize)
        table.add_row(label, left_text, right_text)
        asyncio.sleep(0)

    ds_label = Text("Sources", "grey bold")
    ds_left = Text(", ".join([d.name for d in left.datasets]))
    ds_right = Text(", ".join([d.name for d in right.datasets]))
    table.add_row(ds_label, ds_left, ds_right)
    return table
