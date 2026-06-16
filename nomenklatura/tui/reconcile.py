from typing import Generic, List, Optional, Tuple, Type, cast

from rich.console import RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import DataTable, Footer

from followthemoney import DS, SE, Dataset, StatementEntity, registry
from rigour.ids.wikidata import is_qid

from nomenklatura.judgement import Judgement
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store
from nomenklatura.tui.comparison import render_comparison
from nomenklatura.tui.util import apply_judgement
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.propose import propose_create, propose_enrich
from nomenklatura.wikidata.reconcile import (
    candidate_proxy,
    create_preview,
    rank_candidates,
)
from nomenklatura.wikidata.util import entity_qid
from nomenklatura.wikidata.write import QSCommand


class ReconcileState(Generic[DS, SE]):
    """Drives the interactive review: which person, which ranked candidates, what's queued.

    Iterates persons in the store, holding the current person's ranked Wikidata
    candidates in memory. Already-linked persons are enriched silently and
    skipped. A confirmed candidate records a POSITIVE judgement and queues
    enrichment; "none of the above" queues item creation; skip does neither. The
    accumulated `enrich_commands`/`create_commands` are serialized after the app
    exits.
    """

    def __init__(
        self,
        resolver: Resolver[SE],
        store: Store[DS, SE],
        client: WikidataClient,
        dataset: Dataset,
        algorithm: Type[ScoringAlgorithm],
        aliases: bool = False,
        retrieved: Optional[str] = None,
        user: Optional[str] = None,
        url_base: Optional[str] = None,
    ) -> None:
        self.resolver = resolver
        self.store = store
        self.client = client
        self.dataset = dataset
        self.algorithm = algorithm
        self.config = algorithm.default_config()
        self.aliases = aliases
        self.retrieved = retrieved
        self.user = user
        self.url_base = url_base
        self.view = store.default_view()
        self.latinize = False
        self._iter = self.view.entities()
        self.person: Optional[SE] = None
        # Ranked candidates for the current person: (item, score, display proxy).
        # The proxy is always a StatementEntity (built by candidate_proxy), distinct
        # from the store's SE type.
        self.candidates: List[Tuple[Item, float, StatementEntity]] = []
        # Index into candidates; == len(candidates) means the "none of the above" row.
        self.highlight = 0
        self.enrich_commands: List[QSCommand] = []
        self.create_commands: List[QSCommand] = []

    @property
    def at_create(self) -> bool:
        """True when the highlight sits on the 'none of the above' row."""
        return self.highlight >= len(self.candidates)

    def start(self) -> bool:
        self.resolver.begin()
        return self.load()

    def load(self) -> bool:
        """Advance to the next unlinked person, ranking its candidates.

        Returns False when the person stream is exhausted. Already-linked persons
        are enriched here and skipped over — they need no decision.
        """
        self.person = None
        self.candidates = []
        self.highlight = 0
        for entity in self._iter:
            if not entity.schema.is_a("Person") or entity.id is None:
                continue
            current = self.resolver.get_canonical(entity.id)
            linked = current if is_qid(current) else entity_qid(entity)
            if linked is not None:
                item = self.client.fetch_item(linked)
                if item is not None:
                    self.enrich_commands.extend(
                        propose_enrich(entity, item, self.retrieved)
                    )
                continue
            ranked = rank_candidates(
                self.client, self.dataset, self.algorithm, self.config, entity, self.aliases
            )
            candidates: List[Tuple[Item, float, StatementEntity]] = []
            for item, score in ranked:
                if item.id is None:
                    continue
                # Skip candidates already judged (negative/unsure/positive) — a
                # past decision means "don't suggest this pair again".
                if not self.resolver.check_candidate(entity.id, item.id):
                    continue
                proxy = candidate_proxy(self.dataset, item)
                if proxy is not None:
                    candidates.append((item, score, proxy))
            self.person = entity
            self.candidates = candidates
            return True
        return False

    def confirm(self) -> None:
        if self.person is None or self.person.id is None:
            return
        if self.at_create:
            self.create_commands.extend(propose_create(self.person, self.retrieved))
        else:
            item = self.candidates[self.highlight][0]
            if item.id is not None and self.resolver.check_candidate(
                self.person.id, item.id
            ):
                apply_judgement(
                    self.resolver, self.store, self.person.id, item.id, Judgement.POSITIVE
                )
                self.enrich_commands.extend(
                    propose_enrich(self.person, item, self.retrieved)
                )
                # apply_judgement committed the transaction; reopen for the next read.
                self.resolver.begin()
        self.load()

    def reject(self, judgement: Judgement) -> None:
        """Record a non-positive judgement on the highlighted candidate; drop it.

        Used for "no match" (NEGATIVE) and "unsure": the judgement is written so
        the pair is never suggested again (now or on a later run), and the
        candidate leaves the list without advancing to the next person — so you
        can cull wrong suggestions and then confirm or create.
        """
        if self.person is None or self.person.id is None or self.at_create:
            return
        item = self.candidates[self.highlight][0]
        if item.id is not None:
            apply_judgement(
                self.resolver, self.store, self.person.id, item.id, judgement
            )
            self.resolver.begin()
        del self.candidates[self.highlight]
        if self.highlight > len(self.candidates):
            self.highlight = len(self.candidates)

    def skip(self) -> None:
        self.load()


class ReconcileAppWidget(Widget):
    @property
    def state(self) -> ReconcileState[Dataset, StatementEntity]:
        app = cast("ReconcileApp[Dataset, StatementEntity]", self.app)
        return app.reconcile


def _score_bar(score: float) -> Text:
    """A 10-cell block bar + numeric score, coloured by confidence."""
    width = 10
    filled = max(0, min(width, round(score * width)))
    color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
    bar = "█" * filled + "░" * (width - filled)
    return Text(f"{bar} {score:.2f}", style=color)


def _candidate_row(proxy: StatementEntity) -> Tuple[Text, Text, Text]:
    """Name / birth year / citizenship cells for a candidate row."""
    dates = proxy.get("birthDate", quiet=True)
    born = min(dates)[:4] if dates else ""
    countries = [
        registry.country.caption(c) or c
        for c in proxy.get("citizenship", quiet=True)
    ]
    return (
        Text(proxy.caption or proxy.id or ""),
        Text(born),
        Text(", ".join(countries)),
    )


class CandidateTable(DataTable[Text]):
    pass


class ComparePanel(VerticalScroll):
    # Not focusable: otherwise it steals keyboard focus from the candidate list
    # (its long content makes it scrollable), leaving the arrow keys scrolling
    # the comparison instead of moving the highlight. Mouse wheel still scrolls.
    can_focus = False


class CompareWidget(ReconcileAppWidget):
    def render(self) -> RenderableType:
        state = self.state
        if state.person is None:
            return Text("No more persons to reconcile. Press Q to quit.", justify="center")
        if state.at_create:
            # Preview what creating a new item would write, in the same table
            # shape as a candidate — the person on the left, the proposed new
            # item on the right.
            preview = create_preview(state.dataset, state.person)
            return render_comparison(
                state.view,
                state.person,
                preview,
                0.0,
                latinize=state.latinize,
                score_label="",
            )
        item, score, proxy = state.candidates[state.highlight]
        return render_comparison(
            state.view,
            state.person,
            proxy,
            score,
            latinize=state.latinize,
            url_base=state.url_base,
        )


class ReconcileWidget(Widget):
    def compose(self) -> ComposeResult:
        yield CandidateTable()
        yield ComparePanel(CompareWidget())


class ReconcileApp(App[int], Generic[DS, SE]):
    CSS_PATH = "reconcile.tcss"
    reconcile: ReconcileState[DS, SE]
    # Per table row, the state.highlight it maps to, or None for a non-selectable
    # informational row (e.g. "no candidates"). Keeps the table-row index and the
    # state's candidate index decoupled.
    _row_highlights: List[Optional[int]] = []

    BINDINGS = [
        ("x", "confirm", "Confirm"),
        ("n", "negative", "No match"),
        ("u", "unsure", "Unsure"),
        ("s", "skip", "Skip"),
        ("l", "latinize", "Latinize"),
        ("q", "exit_hard", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield ReconcileWidget()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(CandidateTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.border_title = "Wikidata candidates (↑/↓ to navigate)"
        table.add_column("Score", width=18)
        table.add_column("Name")
        table.add_column("Born", width=6)
        table.add_column("Citizenship", width=24)
        table.add_column("Wikidata", width=12)
        self.reconcile.start()
        self.refresh_candidates()
        self.set_focus(table)

    def refresh_candidates(self) -> None:
        table = self.query_one(CandidateTable)
        table.clear()
        state = self.reconcile
        self._row_highlights = []
        if state.person is not None:
            for index, (item, score, proxy) in enumerate(state.candidates):
                name, born, country = _candidate_row(proxy)
                table.add_row(_score_bar(score), name, born, country, Text(item.id or ""))
                self._row_highlights.append(index)
            if not state.candidates:
                # No search hits: a non-selectable note so the create row has context.
                table.add_row(
                    Text(""),
                    Text("(No candidates found)", style="dim italic"),
                    Text(""), Text(""), Text(""),
                )
                self._row_highlights.append(None)
                create_label = "✚ Create a new item"
            else:
                create_label = "✚ None of the above — create a new item"
            table.add_row(
                Text(""), Text(create_label, style="cyan"), Text(""), Text(""), Text("")
            )
            self._row_highlights.append(len(state.candidates))
            start = self._first_selectable()
            table.move_cursor(row=start)
            state.highlight = self._row_highlights[start] or 0
        self._render_comparison()

    def _first_selectable(self) -> int:
        for row, highlight in enumerate(self._row_highlights):
            if highlight is not None:
                return row
        return 0

    def _render_comparison(self) -> None:
        self.query_one(CompareWidget).refresh(layout=True)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        row = event.cursor_row
        if row < 0 or row >= len(self._row_highlights):
            return
        target = self._row_highlights[row]
        if target is None:
            # Non-selectable row: bounce the cursor to the nearest selectable one.
            self.query_one(CandidateTable).move_cursor(row=self._first_selectable())
            return
        self.reconcile.highlight = target
        self._render_comparison()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.reconcile.confirm()
        self.refresh_candidates()

    def action_confirm(self) -> None:
        self.reconcile.confirm()
        self.refresh_candidates()

    def action_negative(self) -> None:
        self.reconcile.reject(Judgement.NEGATIVE)
        self.refresh_candidates()

    def action_unsure(self) -> None:
        self.reconcile.reject(Judgement.UNSURE)
        self.refresh_candidates()

    def action_skip(self) -> None:
        self.reconcile.skip()
        self.refresh_candidates()

    def action_latinize(self) -> None:
        self.reconcile.latinize = not self.reconcile.latinize
        self._render_comparison()

    def action_exit_hard(self) -> None:
        self.exit(0)
