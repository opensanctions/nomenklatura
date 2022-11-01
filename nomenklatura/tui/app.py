import asyncio
from typing import Optional, Set, Tuple, cast
from rich.text import Text
from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Footer

from nomenklatura.judgement import Judgement
from nomenklatura.loader import Loader
from nomenklatura.resolver import Resolver
from nomenklatura.entity import CE
from nomenklatura.dataset import DS
from nomenklatura.tui.comparison import render_comparison


class DedupeState(object):
    def __init__(
        self,
        resolver: Resolver[CE],
        loader: Loader[DS, CE],
        url_base: Optional[str] = None,
    ):
        self.resolver = resolver
        self.loader = loader
        self.url_base = url_base
        self.latinize = False
        self.message: Optional[str] = None
        self.ignore: Set[Tuple[str, str]] = set()
        self.left: Optional[CE] = None
        self.right: Optional[CE] = None
        self.score = 0.0

    def load(self) -> bool:
        self.left = None
        self.right = None
        for left_id, right_id, score in self.resolver.get_candidates():
            if (left_id, right_id) in self.ignore:
                continue
            if score is None:
                self.ignore.add((left_id, right_id))
                continue
            if not self.resolver.check_candidate(left_id, right_id):
                self.ignore.add((left_id, right_id))
                continue
            self.left = self.loader.get_entity(left_id)
            self.right = self.loader.get_entity(right_id)
            self.score = score
            if self.left is not None and self.right is not None:
                if self.left.schema.can_match(self.right.schema):
                    return True
            self.ignore.add((left_id, right_id))
        return False

    def decide(self, judgement: Judgement) -> None:
        if self.left is not None and self.right is not None:
            self.resolver.decide(self.left.id, self.right.id, judgement=judgement)
        self.load()

    def save(self):
        self.resolver.save()


class DedupeWidget(Widget):
    def on_mount(self) -> None:
        self.styles.height = "auto"

    @property
    def dedupe(self):
        return cast(DedupeApp, self.app).dedupe

    def render(self) -> RenderableType:
        if self.dedupe.message is not None:
            return Text(self.dedupe.message, justify="center")
        if self.dedupe.left and self.dedupe.right:
            return render_comparison(
                self.dedupe.loader,
                self.dedupe.left,
                self.dedupe.right,
                self.dedupe.score,
                latinize=self.dedupe.latinize,
                url_base=self.dedupe.url_base,
            )
        return Text("No candidates.", justify="center")


class DedupeApp(App):
    dedupe: DedupeState

    BINDINGS = [
        ("x", "positive", "Match"),
        ("n", "negative", "No match"),
        ("u", "unsure", "Unsure"),
        ("l", "latinize", "Latinize"),
        ("s", "save", "Save"),
        ("w", "exit_save", "Quit & save"),
        ("q", "exit_hard", "Quit"),
    ]

    def on_mount(self) -> None:
        self.screen.styles.layout = "vertical"

    async def decide(self, judgement: Judgement) -> None:
        self.dedupe.decide(judgement)
        self.force_render()

    def force_render(self) -> None:
        self.widget.refresh(layout=True)

    async def save_resolver(self) -> None:
        self.dedupe.message = "Saving..."
        self.force_render()
        self.dedupe.save()
        self.dedupe.message = "Saved."
        self.force_render()
        await asyncio.sleep(1)
        self.dedupe.message = None

    async def action_positive(self) -> None:
        await self.decide(Judgement.POSITIVE)

    async def action_negative(self) -> None:
        await self.decide(Judgement.NEGATIVE)

    async def action_unsure(self) -> None:
        await self.decide(Judgement.UNSURE)

    async def action_latinize(self) -> None:
        self.dedupe.latinize = not self.dedupe.latinize
        self.force_render()

    async def action_save(self) -> None:
        await self.save_resolver()
        # await self.load_candidate()
        self.force_render()

    async def action_exit_save(self) -> None:
        await self.save_resolver()
        self.exit()

    async def action_exit_hard(self) -> None:
        self.exit()

    def compose(self) -> ComposeResult:
        self.dedupe.load()
        self.widget = DedupeWidget()
        yield self.widget
        yield Footer()
