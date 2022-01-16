from typing import TYPE_CHECKING
from normality import latinize_text
from rich.console import RenderableType  # type: ignore
from rich.table import Table  # type: ignore
from rich.text import Text  # type: ignore
from textual.widget import Widget  # type: ignore
from followthemoney.types import registry
from followthemoney.property import Property

from nomenklatura.entity import CompositeEntity
from nomenklatura.tui.util import comparison_props

if TYPE_CHECKING:
    from nomenklatura.tui.app import DedupeApp


class Comparison(Widget):
    def __init__(self, dedupe: "DedupeApp") -> None:
        super().__init__()
        self.dedupe = dedupe

    def render_column(self, entity: CompositeEntity) -> Text:
        return Text.assemble(
            (entity.schema.label, "blue"), " [%s]" % entity.id, no_wrap=True
        )

    def render_values(
        self, prop: Property, entity: CompositeEntity, other: CompositeEntity
    ) -> Text:
        values = entity.get(prop, quiet=True)
        other_values = other.get_type_values(prop.type)
        text = Text()
        for i, value in enumerate(sorted(values)):
            if i > 0:
                text.append(" · ")
            caption = prop.type.caption(value)
            if prop.type == registry.entity:
                caption = self.dedupe.loader.get_entity(value).caption
            score = prop.type.compare_sets([value], other_values)
            if self.dedupe.latinize:
                caption = latinize_text(caption) or caption
            style = "default"
            if score > 0.7:
                style = "yellow"
            if score > 0.95:
                style = "green"
            if caption is not None:
                text.append(caption, style)
        return text

    def render(self) -> RenderableType:
        if self.dedupe.left is None or self.dedupe.right is None:
            return Text("No candidates loaded.", justify="center")

        table = Table(expand=True)
        score = "Score: %.3f" % self.dedupe.score
        table.add_column(score, justify="right", no_wrap=True, ratio=2)
        table.add_column(self.render_column(self.dedupe.left), ratio=5)
        table.add_column(self.render_column(self.dedupe.right), ratio=5)

        for prop in comparison_props(self.dedupe.left, self.dedupe.right):
            label = Text(prop.label, "white bold")
            left_text = self.render_values(prop, self.dedupe.left, self.dedupe.right)
            right_text = self.render_values(prop, self.dedupe.right, self.dedupe.left)
            table.add_row(label, left_text, right_text)
        return table
