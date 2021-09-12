from normality import latinize_text
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text
from textual.widget import Widget
from followthemoney.types import registry

from nomenklatura.tui.util import comparison_props


class Comparison(Widget):
    def __init__(self, dedupe):
        super().__init__()
        self.dedupe = dedupe

    def render_column(self, entity):
        return Text.assemble(
            (entity.schema.label, "blue"), " [%s]" % entity.id, no_wrap=True
        )

    def render_values(self, prop, entity, other):
        values = entity.get(prop, quiet=True)
        other_values = other.get_type_values(prop.type)
        text = Text()
        for i, value in enumerate(values):
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
