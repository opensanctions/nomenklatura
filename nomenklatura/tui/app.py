import asyncio
from rich.text import Text  # type: ignore
from textual.app import App
from textual.widgets import Footer, ScrollView
from followthemoney.dedupe.judgement import Judgement

from nomenklatura.tui.comparison import render_comparison

# from textual import log
# from textual.reactive import Reactive


class DedupeApp(App):
    def __init__(self, loader=None, resolver=None, **kwargs):
        super().__init__(**kwargs)
        self.loader = loader
        self.resolver = resolver
        self.latinize = False
        self.ignore = set()

    async def load_candidate(self):
        self.comp = Text("No candidates loaded.", justify="center")
        self.left = None
        self.right = None
        self.score = 0.0
        for left_id, right_id, score in self.resolver.get_candidates(limit=1000):
            if (left_id, right_id) in self.ignore:
                continue
            self.left = self.loader.get_entity(left_id)
            self.right = self.loader.get_entity(right_id)
            self.score = score
            if self.left is not None and self.right is not None:
                if self.left.schema in self.right.schema.matchable_schemata:
                    self.score = score
                    self.comp = await render_comparison(
                        self.loader,
                        self.left,
                        self.right,
                        score,
                        latinize=self.latinize,
                    )
                    break
            self.ignore.add((left_id, right_id))
            asyncio.sleep(0)

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
            self.resolver.decide(self.left.id, self.right.id, judgement)
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
        self.resolver.save()
        self.comp = await render_comparison(
            self.loader, self.left, self.right, self.score, latinize=self.latinize
        )
        await self.force_render()

    async def action_quit(self) -> None:
        self.comp = Text("Saving...", justify="center")
        await self.force_render()
        self.resolver.save()
        await self.shutdown()

    async def action_exit(self) -> None:
        await self.shutdown()

    async def force_render(self) -> None:
        self.scroll.home()
        self.scroll.refresh(layout=True)
        await self.scroll.update(self.comp)

    async def on_mount(self) -> None:
        await self.load_candidate()
        self.scroll = ScrollView(self.comp)
        self.footer = Footer()
        await self.view.dock(self.footer, edge="bottom")
        await self.view.dock(self.scroll, edge="top")
