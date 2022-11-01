import asyncio
from typing import TYPE_CHECKING, Optional
from normality import latinize_text
from rich.table import Table
from rich.text import Text
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.loader import Loader
from nomenklatura.tui.util import comparison_props


def render_column(entity: CE) -> Text:
    return Text.assemble(
        (entity.schema.label, "blue"), " [%s]" % entity.id, no_wrap=True
    )


def render_values(
    loader: Loader[DS, CE], prop: Property, entity: CE, other: CE, latinize: bool
) -> Text:
    values = entity.get(prop, quiet=True)
    other_values = other.get_type_values(prop.type)
    text = Text()
    for i, value in enumerate(sorted(values)):
        caption = prop.type.caption(value)
        if prop.type == registry.entity:
            sub = loader.get_entity(value)
            if sub is not None:
                caption = sub.caption
        score = prop.type.compare_sets([value], other_values)
        if latinize:
            caption = latinize_text(caption) or caption
        if prop.name == "wikidataId":
            caption = f"https://wikidata.org/wiki/{value}"
        style = "default"
        if score > 0.7:
            style = "yellow"
        if score > 0.95:
            style = "green"
        if caption is not None:
            if i > 0:
                text.append(" · ", "gray")
            text.append(caption, style)
    return text


def render_comparison(
    loader: Loader[DS, CE],
    left: CE,
    right: CE,
    score: float,
    latinize: bool = False,
    url_base: Optional[str] = None,
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
        left_text = render_values(loader, prop, left, right, latinize)
        right_text = render_values(loader, prop, right, left, latinize)
        table.add_row(label, left_text, right_text)

    ds_label = Text("Sources", "grey bold")
    ds_left = Text(", ".join(left.datasets))
    ds_right = Text(", ".join(right.datasets))
    table.add_row(ds_label, ds_left, ds_right)

    if url_base is not None:
        ds_label = Text("URL", "grey bold")
        ds_left = Text(url_base % left.id)
        ds_right = Text(url_base % right.id)
        table.add_row(ds_label, ds_left, ds_right)

    return table
