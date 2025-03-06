import asyncio
from typing import Dict, Optional, Set, Tuple, cast

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Footer, Label, ListItem, ListView, Static

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.resolver.edge import Edge
from nomenklatura.store import Store
from nomenklatura.tui.comparison import render_comparison

HISTORY_LENGTH = 20


class DedupeState(object):
    def __init__(
        self,
        resolver: Resolver[CE],
        store: Store[DS, CE],
        url_base: Optional[str] = None,
    ):
        self.store = store
        self.resolver = resolver
        self.view = store.default_view(external=True)
        self.url_base = url_base
        self.latinize = False
        self.message: Optional[str] = None
        self.ignore: Set[Tuple[str, str]] = set()
        self.left: Optional[CE] = None
        self.right: Optional[CE] = None
        self.score = 0.0
        self.recents: Dict[str, CE] = dict()

    def load(self) -> bool:
        self.left = None
        self.right = None
        self.resolver.begin()
        for left_id, right_id, score in self.resolver.get_candidates():
            left_id = self.resolver.get_canonical(left_id)
            right_id = self.resolver.get_canonical(right_id)
            if (left_id, right_id) in self.ignore:
                continue
            if score is None:
                self.ignore.add((left_id, right_id))
                continue
            if not self.resolver.check_candidate(left_id, right_id):
                self.ignore.add((left_id, right_id))
                continue
            self.left = self.view.get_entity(left_id)
            self.right = self.view.get_entity(right_id)
            self.score = score
            if self.left is not None and self.right is not None:
                if self.left.schema == self.right.schema:
                    return True
                if self.left.schema.can_match(self.right.schema):
                    return True
            self.ignore.add((left_id, right_id))
        return False

    def decide(self, judgement: Judgement) -> None:
        if self.left is not None and self.left.id is not None:
            if self.right is not None and self.right.id is not None:
                # Since we don't have an unresolved store as well as the resolved one,
                # hold on to pre-merge entities to show in history.
                self.recents[self.left.id] = self.left
                self.recents[self.right.id] = self.right
                canonical_id = self.resolver.decide(
                    self.left.id,
                    self.right.id,
                    judgement=judgement,
                )
                self.store.update(canonical_id)
        self.resolver.commit()
        self.load()

    def edit(self, edge: Edge, judgement: Judgement) -> None:
        self.resolver.decide(edge.source, edge.target, judgement)
        self.store.update(edge.source)
        self.store.update(edge.target)
        self.resolver.commit()
        self.load()


class DedupeAppWidget(Widget):
    @property
    def dedupe(self) -> DedupeState:
        return cast(DedupeApp, self.app).dedupe


class HistoryItem(Static, DedupeAppWidget):
    def __init__(self, edge: Edge) -> None:
        self.edge = edge
        source = self.dedupe.recents.get(edge.source.id, None)
        target = self.dedupe.recents.get(edge.target.id, None)
        if target is None:
            target = self.dedupe.view.get_entity(edge.target.id)
        source_str = f"src: {edge.source.id}"
        if source:
            source_str += f"\n     {source.caption}"
        target_str = f"tgt: {edge.target.id}"
        if target:
            target_str += f"\n     {target.caption}"

        content = (
            f"{edge.created_at if edge.created_at else 'unknown time'}\n"
            f"{source_str}\n"
            f"{target_str}\n"
            f"{edge.user} decided {edge.judgement.value}"
        )
        super().__init__(content)


class ConfirmEditModal(ModalScreen[bool]):
    edge: Optional[Edge] = None
    judgement: Optional[Judgement] = None

    def compose(self) -> ComposeResult:
        assert self.edge is not None
        assert self.judgement is not None
        message = f"Change {self.edge.source.id} -> {self.edge.target.id} to {self.judgement.value}?"
        yield Grid(
            Label(message, id="question"),
            Button("Yes", variant="error", id="yes"),
            Button("No", variant="primary", id="no"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)


class HistoryListView(ListView):
    BINDINGS = [
        ("x", "positive", "Match"),
        ("n", "negative", "No match"),
        ("u", "unsure", "Unsure"),
        ("d", "delete", "No judgement"),
    ]

    async def action_positive(self) -> None:
        await self.trigger_edit(Judgement.POSITIVE)

    async def action_negative(self) -> None:
        await self.trigger_edit(Judgement.NEGATIVE)

    async def action_unsure(self) -> None:
        await self.trigger_edit(Judgement.UNSURE)

    async def action_delete(self) -> None:
        await self.trigger_edit(Judgement.NO_JUDGEMENT)

    async def trigger_edit(self, judgement: Judgement) -> None:
        selected = self.highlighted_child
        if selected is None:
            return
        edge = selected.query_one(HistoryItem).edge
        await cast(DedupeApp, self.app).edit(edge, judgement)


class HistoryWidget(DedupeAppWidget):
    list_view: ListView

    def on_mount(self) -> None:
        self.border_title = "History"
        self.reload_history()

    def compose(self) -> ComposeResult:
        self.list_view = HistoryListView()
        yield Static(
            (
                "Tab to toggle between dedupe and history.\n"
                "Arrow up/down to select history to edit."
            ),
            classes="help",
        )
        yield self.list_view

    def reload_history(self) -> None:
        self.list_view.clear()
        for edge in self.dedupe.resolver.get_judgements(HISTORY_LENGTH):
            self.list_view.append(ListItem(HistoryItem(edge)))
        self.list_view.scroll_home(animate=False)


class DedupeWidget(Widget):
    def compose(self) -> ComposeResult:
        yield CompareWidget()
        yield HistoryWidget()


class CompareWidget(DedupeAppWidget, can_focus=True):
    def render(self) -> RenderableType:
        if self.dedupe.message is not None:
            return Text(self.dedupe.message, justify="center")
        if self.dedupe.left and self.dedupe.right:
            return render_comparison(
                self.dedupe.view,
                self.dedupe.left,
                self.dedupe.right,
                self.dedupe.score,
                latinize=self.dedupe.latinize,
                url_base=self.dedupe.url_base,
            )
        return Text("No candidates.", justify="center")


class DedupeApp(App[int]):
    CSS_PATH = "app.tcss"
    dedupe: DedupeState

    BINDINGS = [
        ("x", "positive", "Match"),
        ("n", "negative", "No match"),
        ("u", "unsure", "Unsure"),
        ("l", "latinize", "Latinize"),
        ("q", "exit_hard", "Quit"),
    ]

    async def decide(self, judgement: Judgement) -> None:
        self.dedupe.decide(judgement)
        self.force_render()

    async def edit(self, edge: Edge, judgement: Judgement) -> None:
        async def handle_confirmation(confirmed: bool | None) -> None:
            if confirmed:
                self.dedupe.edit(edge, judgement)
                self.force_render()
            else:
                self.dedupe.message = "Canceled edit."
                self.force_render()
                await asyncio.sleep(1)
                self.dedupe.message = None
                self.force_render()

        screen = ConfirmEditModal()
        screen.edge = edge
        screen.judgement = judgement
        self.app.push_screen(screen, handle_confirmation)

    def force_render(self) -> None:
        self.query_one(CompareWidget).refresh(layout=True)
        self.query_one(HistoryWidget).reload_history()
        self.query_one(HistoryWidget).refresh(layout=True)

    async def action_positive(self) -> None:
        await self.decide(Judgement.POSITIVE)

    async def action_negative(self) -> None:
        await self.decide(Judgement.NEGATIVE)

    async def action_unsure(self) -> None:
        await self.decide(Judgement.UNSURE)

    async def action_latinize(self) -> None:
        self.dedupe.latinize = not self.dedupe.latinize
        self.force_render()

    async def action_exit_hard(self) -> None:
        self.exit(0)

    def compose(self) -> ComposeResult:
        self.dedupe.load()
        yield DedupeWidget()
        yield Footer()
