from typing import Dict, Set, Tuple, Generic, Generator
from itertools import combinations
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich import box

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.statement.statement import Statement


class ConflictingMatchReporter(Generic[CE]):
    def __init__(self, view: View[DS, CE], resolver: Resolver[CE], threshold: float):
        self.console = Console()
        self.view = view
        self.resolver = resolver
        self.threshold = threshold
        self.matches: Dict[str, Set[str]] = defaultdict(set)

    def check_match(self, score: float, left_id: str, right_id: str) -> None:
        if score > self.threshold:
            self.matches[left_id].add(right_id)
            self.matches[right_id].add(left_id)

    def get_conflicting_matches(self) -> Generator[Tuple[str, str, str], None, None]:
        for candidate_id, matches in self.matches.items():
            for left_id, right_id in combinations(matches, 2):
                judgement = self.resolver.get_judgement(left_id, right_id)
                if judgement == Judgement.NEGATIVE:
                    yield candidate_id, left_id, right_id

    @staticmethod
    def _sort_key(stmt: Statement) -> Tuple[str, str, int, str, int]:
        prop_order = 0 if stmt.prop == "name" else 1
        lang_order = 0 if stmt.lang is None else 1
        return (stmt.dataset, stmt.entity_id, prop_order, stmt.value, lang_order)

    def report_conflicting_match(self, title: str, entity: CE) -> None:
        if entity.id is None:
            return
        statements = []
        for stmt in entity.statements:
            if stmt.prop in {"name", "alias"}:
                statements.append(stmt)

        table = Table(box=box.SIMPLE, expand=True)
        table.add_column("Dataset", style="cyan", max_width=20)
        table.add_column("Entity ID", style="magenta", max_width=30)
        table.add_column("Prop", style="blue")
        table.add_column("Lang", style="green")
        table.add_column("Name", style="yellow")

        for stmt in sorted(statements, key=self._sort_key):
            table.add_row(
                stmt.dataset, stmt.entity_id, stmt.prop, stmt.lang, "• " + stmt.value
            )

        self.console.print(f"[bold]{title}[/bold]:")
        self.console.print(f"{entity.id}")
        self.console.print(table)

    def report(self) -> None:
        conflicts = list(self.get_conflicting_matches())
        if not conflicts:
            return

        self.console.print("[bold]Potential conflicting matches found:\n[/bold]")
        for candidate_id, left_id, right_id in self.get_conflicting_matches():
            left = self.view.get_entity(left_id)
            right = self.view.get_entity(right_id)
            candidate = self.view.get_entity(candidate_id)

            if candidate:
                self.report_conflicting_match("Candidate", candidate)
            if left:
                self.report_conflicting_match("Left side of negative decision", left)
            if right:
                self.report_conflicting_match("Right side of negative decision", right)
