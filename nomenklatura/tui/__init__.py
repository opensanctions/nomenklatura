import sys
from normality import latinize_text
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import App
from textual import log
from textual.widget import Widget
from textual.widgets import Footer
from followthemoney.types import registry
from followthemoney.dedupe.judgement import Judgement

# from textual.reactive import Reactive


class Comparison(Widget):
    def __init__(self, dedupe):
        super().__init__()
        self.dedupe = dedupe

    def compare_props(self):
        props = set(self.dedupe.left.iterprops())
        props.update(self.dedupe.right.iterprops())
        weights = {p.name: 0 for p in props}
        for prop in props:
            for schema in (self.dedupe.left.schema, self.dedupe.right.schema):
                if prop.name in schema.caption:
                    weights[prop.name] -= 2
                if prop.name in schema.featured:
                    weights[prop.name] -= 1

        key = lambda p: (weights[p.name], p.label)
        for prop in sorted(props, key=key):
            if prop.hidden:
                continue
            # if prop.type == registry.entity:
            #     continue
            yield prop

    def render_column(self, entity):
        return Text.assemble((entity.schema.label, "blue"), " [%s]" % entity.id)

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
            return Text("Loading...", justify="center")

        table = Table(expand=True)
        score = "Score: %.3f" % self.dedupe.score
        table.add_column(score, justify="right", no_wrap=True, ratio=2)
        table.add_column(self.render_column(self.dedupe.left), ratio=5)
        table.add_column(self.render_column(self.dedupe.right), ratio=5)

        for prop in self.compare_props():
            label = Text(prop.label, "white bold")
            left_text = self.render_values(prop, self.dedupe.left, self.dedupe.right)
            right_text = self.render_values(prop, self.dedupe.right, self.dedupe.left)
            table.add_row(label, left_text, right_text)
        return table


class DedupeApp(App):
    def __init__(self, loader=None, resolver=None, **kwargs):
        super().__init__(**kwargs)
        self.loader = loader
        self.resolver = resolver
        self.load_candidate()

    def load_candidate(self):
        self.left = None
        self.right = None
        self.score = 0.0
        for left_id, right_id, score in self.resolver.get_candidates(limit=1):
            self.left = self.loader.get_entity(left_id)
            self.right = self.loader.get_entity(right_id)
            self.score = score

    async def on_load(self, event):
        await self.bind("x", "positive", "Match")
        await self.bind("n", "negative", "No match")
        await self.bind("u", "unsure", "Unsure")
        await self.bind("s", "save", "Save")
        await self.bind("q", "quit", "Quit")
        # await self.bind("ctrl-c", "quit", "Quit")

    def decide(self, judgement):
        if self.left is not None and self.right is not None:
            self.resolver.decide(self.left.id, self.right.id, judgement)
        self.load_candidate()
        if self.left is None or self.right is None:
            self.shutdown()
        self.comp.refresh()

    async def action_positive(self) -> None:
        self.decide(Judgement.POSITIVE)

    async def action_negative(self) -> None:
        self.decide(Judgement.NEGATIVE)

    async def action_unsure(self) -> None:
        self.decide(Judgement.UNSURE)

    async def action_save(self) -> None:
        self.resolver.save("resolver.ijson")

    async def on_mount(self) -> None:
        self.comp = Comparison(self)
        self.footer = Footer()
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.comp, edge="top")


if __name__ == "__main__":
    from pathlib import Path
    from nomenklatura.loader import FileLoader
    from nomenklatura.resolver import Resolver
    from nomenklatura.index import Index
    from nomenklatura.xref import xref

    resolver = Resolver()
    loader = FileLoader(Path(sys.argv[1]))
    index = Index(loader)
    index.build()
    xref(index, resolver, list(loader))
    DedupeApp.run(
        title="NK De-duplication", log="textual.log", loader=loader, resolver=resolver
    )
