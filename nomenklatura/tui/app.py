from rich.text import Text  # type: ignore
from textual.app import App
from textual.widgets import Footer, ScrollView
from followthemoney.dedupe.judgement import Judgement

from nomenklatura.resolver import Resolver
from nomenklatura.tui.comparison import render_comparison

# from textual import log
# from textual.reactive import Reactive


class DedupeApp(App):
    def __init__(self, loader=None, resolver=None, **kwargs):
        super().__init__(**kwargs)
        self.loader = loader
        self.resolver: Resolver = resolver
        self.latinize = False
        self.ignore = set()

    async def load_candidate(self):
        self.comp = Text("No candidates loaded.", justify="center")
        self.left = None
        self.right = None
        self.score = 0.0
        async for left_id, right_id, score in self.resolver.get_candidates(limit=100):
            if (left_id, right_id) in self.ignore:
                continue
            left = await self.loader.get_entity(left_id)
            right = await self.loader.get_entity(right_id)
            if left is not None and right is not None:
                if left.schema in right.schema.matchable_schemata:
                    self.left = left
                    self.right = right
                    self.score = score
                    self.comp = await render_comparison(
                        self.loader, left, right, score, latinize=self.latinize
                    )
                    break
            self.ignore.add((left_id, right_id))

    async def on_load(self, event):
        await self.bind("x", "positive", "Match")
        await self.bind("n", "negative", "No match")
        await self.bind("u", "unsure", "Unsure")
        await self.bind("l", "latinize", "Latinize")
        await self.bind("s", "save", "Save")
        await self.bind("w", "quit", "Save & exit")
        await self.bind("q", "exit", "Exit now")

    async def decide(self, judgement):
        if self.left is not None and self.right is not None:
            await self.resolver.decide(self.left.id, self.right.id, judgement)
        await self.load_candidate()
        if self.left is None or self.right is None:
            await self.shutdown()
            return
        await self.force_render()

    async def action_positive(self) -> None:
        await self.decide(Judgement.POSITIVE)

    async def action_negative(self) -> None:
        await self.decide(Judgement.NEGATIVE)

    async def action_unsure(self) -> None:
        await self.decide(Judgement.UNSURE)

    async def action_latinize(self) -> None:
        self.latinize = not self.latinize
        self.comp = await render_comparison(
            self.loader, self.left, self.right, self.score, latinize=self.latinize
        )
        await self.force_render()

    async def action_save(self) -> None:
        self.comp = Text("Saving...", justify="center")
        await self.force_render()
        await self.resolver.save()
        self.comp = await render_comparison(
            self.loader, self.left, self.right, self.score, latinize=self.latinize
        )
        await self.force_render()

    async def action_quit(self) -> None:
        self.comp = Text("Saving...", justify="center")
        await self.force_render()
        await self.resolver.save()
        await self.shutdown()

    async def action_exit(self) -> None:
        await self.shutdown()

    async def force_render(self) -> None:
        # self.comp.refresh()
        self.scroll.home()
        # self.scroll.layout.require_update()
        self.scroll.refresh(layout=True)
        await self.scroll.update(self.comp)
        # self.scroll.refresh()

    async def on_mount(self) -> None:
        await self.load_candidate()
        # self.comp = Comparison(self)
        self.scroll = ScrollView(self.comp)
        self.footer = Footer()
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.scroll, edge="top")
