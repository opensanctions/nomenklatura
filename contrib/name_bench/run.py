"""Run a named comparator over cases.csv, or summarise a stored run.

Two modes:

    # Run mode: execute a comparator, store per-case results.
    python contrib/name_comparison/run.py -c levenshtein

    # Summarise mode: re-render metrics from a stored run.
    python contrib/name_comparison/run.py -s run_data/levenshtein-20260428-143010.csv

Run mode writes a timestamped per-case CSV under
`contrib/name_comparison/run_data/` and prints a summary
(confusion matrix overall + by case_group + by category, plus
top-N disagreements). Summarise mode skips the run and just
re-reads + summarises a stored file — useful for re-thresholding
(`-s file.csv -t 0.8`) or sharing a result without re-running.

Each iteration on the spec means adding a new entry to
`COMPARATORS` and re-running. Stored CSVs are diffable:
`qsv diff old.csv new.csv` surfaces the cases that flipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table

# Make the local `comparators` package importable when run.py is invoked
# directly (without rigour being installed in editable mode pointing here).
sys.path.insert(0, str(Path(__file__).parent))

from comparators import COMPARATORS, Comparator  # noqa: E402


HERE = Path(__file__).parent
DEFAULT_CSV = HERE / "cases.csv"
DEFAULT_RUN_DATA = HERE / "run_data"
DEFAULT_THRESHOLD = 0.7


@dataclass
class CaseResult:
    case_group: str
    case_id: str
    schema: str
    name1: str
    name2: str
    is_match: bool
    quality: str
    category: str
    notes: str
    score: float
    threshold: float

    @property
    def predicted_match(self) -> bool:
        return self.score >= self.threshold

    @property
    def outcome(self) -> str:
        if self.is_match and self.predicted_match:
            return "TP"
        if self.is_match and not self.predicted_match:
            return "FN"
        if not self.is_match and self.predicted_match:
            return "FP"
        return "TN"


# --- IO ---


def compute_case_id(case_group: str, schema: str, name1: str, name2: str) -> str:
    """Stable 8-char hex id derived from (case_group, schema, name1, name2).

    cases.csv doesn't carry a `case_id` column — managing sequential ids
    by hand was annoying when iterating on the test set. The id is
    computed at load time and emitted into per-case dump CSVs so qsv
    diff between runs still works.
    """
    h = hashlib.blake2b(
        f"{case_group}|{schema}|{name1}|{name2}".encode("utf-8"),
        digest_size=4,
    )
    return h.hexdigest()


QUALITY_TIERS = ("STRONG", "MEDIUM", "WEAK")
DEFAULT_QUALITY = "MEDIUM"


def load_cases(csv_path: Path) -> List[Dict[str, str]]:
    """Load cases.csv, synthesise `case_id`, normalise `quality`.

    `quality` is optional in the CSV; blank or missing values default to
    `MEDIUM`. Values are normalised to upper case; unknown values fall back
    to `MEDIUM` with a stderr warning.
    """
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    seen: Dict[str, Dict[str, str]] = {}
    out: List[Dict[str, str]] = []
    for row in rows:
        cid = compute_case_id(
            row["case_group"], row["schema"], row["name1"], row["name2"]
        )
        if cid in seen:
            sys.stderr.write(
                f"WARN: duplicate case_id {cid}: "
                f"{(row['case_group'], row['schema'], row['name1'], row['name2'])}\n"
            )
        seen[cid] = row
        row["case_id"] = cid
        q = (row.get("quality") or "").strip().upper()
        if q == "":
            q = DEFAULT_QUALITY
        elif q not in QUALITY_TIERS:
            sys.stderr.write(
                f"WARN: unknown quality {q!r} on {cid}; defaulting to {DEFAULT_QUALITY}\n"
            )
            q = DEFAULT_QUALITY
        row["quality"] = q
        out.append(row)
    return out


def evaluate(
    rows: List[Dict[str, str]], comparator: Comparator, threshold: float
) -> List[CaseResult]:
    out: List[CaseResult] = []
    for row in rows:
        score = comparator(row["name1"], row["name2"], row["schema"])
        out.append(
            CaseResult(
                case_group=row["case_group"],
                case_id=row["case_id"],
                schema=row["schema"],
                name1=row["name1"],
                name2=row["name2"],
                is_match=row["is_match"].lower() == "true",
                quality=row.get("quality", DEFAULT_QUALITY),
                category=row.get("category", ""),
                notes=row.get("notes", ""),
                score=score,
                threshold=threshold,
            )
        )
    return out


DUMP_FIELDS = [
    "case_group", "case_id", "schema", "name1", "name2",
    "is_match", "quality", "category", "notes",
    "score", "predicted_match", "outcome",
]


def dump_csv(results: List[CaseResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DUMP_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "case_group": r.case_group,
                    "case_id": r.case_id,
                    "schema": r.schema,
                    "name1": r.name1,
                    "name2": r.name2,
                    "is_match": "true" if r.is_match else "false",
                    "quality": r.quality,
                    "category": r.category,
                    "notes": r.notes,
                    "score": f"{r.score:.4f}",
                    "predicted_match": "true" if r.predicted_match else "false",
                    "outcome": r.outcome,
                }
            )


def load_results(path: Path, threshold: float) -> List[CaseResult]:
    """Reconstruct CaseResult list from a dumped CSV. Re-derives outcome
    from score + caller-supplied threshold (so summarising at a different
    threshold is a single arg change, not a re-run)."""
    out: List[CaseResult] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out.append(
                CaseResult(
                    case_group=row["case_group"],
                    case_id=row["case_id"],
                    schema=row["schema"],
                    name1=row["name1"],
                    name2=row["name2"],
                    is_match=row["is_match"].lower() == "true",
                    quality=row.get("quality", DEFAULT_QUALITY),
                    category=row.get("category", ""),
                    notes=row.get("notes", ""),
                    score=float(row["score"]),
                    threshold=threshold,
                )
            )
    return out


# --- Metrics ---


def confusion(results: List[CaseResult]) -> Dict[str, float]:
    tp = sum(1 for r in results if r.outcome == "TP")
    fp = sum(1 for r in results if r.outcome == "FP")
    tn = sum(1 for r in results if r.outcome == "TN")
    fn = sum(1 for r in results if r.outcome == "FN")
    n = len(results)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    acc = (tp + tn) / n if n else 0.0
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": p, "recall": r, "f1": f1, "accuracy": acc,
    }


# --- Rendering ---


def metrics_table(title: str, rows: List[tuple], console: Console) -> None:
    """rows: list of (label, metrics_dict)."""
    table = Table(title=title, show_lines=False)
    table.add_column("")
    table.add_column("n", justify="right")
    table.add_column("TP", justify="right", style="green")
    table.add_column("FP", justify="right", style="yellow")
    table.add_column("TN", justify="right")
    table.add_column("FN", justify="right", style="red")
    table.add_column("P", justify="right")
    table.add_column("R", justify="right")
    table.add_column("F1", justify="right", style="cyan")
    table.add_column("Acc", justify="right")
    for label, m in rows:
        table.add_row(
            label,
            str(int(m["n"])),
            str(int(m["tp"])),
            str(int(m["fp"])),
            str(int(m["tn"])),
            str(int(m["fn"])),
            f"{m['precision']:.3f}",
            f"{m['recall']:.3f}",
            f"{m['f1']:.3f}",
            f"{m['accuracy']:.3f}",
        )
    console.print(table)


def print_disagreements(results: List[CaseResult], n: int, console: Console) -> None:
    fps = sorted((r for r in results if r.outcome == "FP"), key=lambda r: -r.score)[:n]
    fns = sorted((r for r in results if r.outcome == "FN"), key=lambda r: r.score)[:n]

    def render(title: str, rows: List[CaseResult]) -> None:
        if not rows:
            return
        table = Table(title=title)
        table.add_column("group/id")
        table.add_column("schema")
        table.add_column("name1")
        table.add_column("name2")
        table.add_column("score", justify="right")
        for r in rows:
            table.add_row(
                f"{r.case_group}/{r.case_id}",
                r.schema, r.name1, r.name2, f"{r.score:.3f}",
            )
        console.print(table)

    render(f"Top {len(fps)} false positives (highest scoring non-matches)", fps)
    render(f"Top {len(fns)} false negatives (lowest scoring matches)", fns)


def print_summary(
    results: List[CaseResult], threshold: float, top: int, console: Console
) -> None:
    console.print(f"[bold]Cases[/bold]: {len(results)}    [bold]Threshold[/bold]: {threshold}")
    console.print()

    metrics_table("Overall", [("all", confusion(results))], console)

    by_group: Dict[str, List[CaseResult]] = defaultdict(list)
    for r in results:
        by_group[r.case_group].append(r)
    console.print()
    metrics_table(
        "By case_group",
        sorted((g, confusion(rs)) for g, rs in by_group.items()),
        console,
    )

    # Per-quality slice. Tier order is fixed (STRONG → MEDIUM → WEAK);
    # this orders the table the same way the calibration check below
    # expects scores to walk monotonically.
    by_quality: Dict[str, List[CaseResult]] = defaultdict(list)
    for r in results:
        by_quality[r.quality].append(r)
    console.print()
    metrics_table(
        "By quality (STRONG-tier failures = bugs; WEAK-tier are tolerated)",
        [(q, confusion(by_quality[q])) for q in QUALITY_TIERS if q in by_quality],
        console,
    )

    print_calibration(by_quality, console)
    print_strong_failures(results, console)

    by_category: Dict[str, List[CaseResult]] = defaultdict(list)
    for r in results:
        if r.category:
            by_category[r.category].append(r)
    if by_category:
        console.print()
        metrics_table(
            "By category (labelled only)",
            sorted((c, confusion(rs)) for c, rs in by_category.items()),
            console,
        )

    if top > 0:
        console.print()
        print_disagreements(results, top, console)


def print_calibration(
    by_quality: Dict[str, List[CaseResult]], console: Console
) -> None:
    """Score-curve monotonicity check: STRONG match scores should sit
    above MEDIUM, MEDIUM above WEAK; symmetrically on the non-match side.
    Inversions or ties between adjacent tiers indicate the curve isn't
    differentiating cleanly — a calibration concern.
    """
    means: Dict[Tuple[str, bool], float] = {}
    for q in QUALITY_TIERS:
        for is_match in (True, False):
            scores = [r.score for r in by_quality.get(q, []) if r.is_match == is_match]
            if scores:
                means[(q, is_match)] = sum(scores) / len(scores)

    table = Table(title="Mean score by (quality, label) — should walk monotonically")
    table.add_column("quality")
    table.add_column("matches", justify="right")
    table.add_column("non-matches", justify="right")
    for q in QUALITY_TIERS:
        m = means.get((q, True))
        n = means.get((q, False))
        table.add_row(
            q,
            f"{m:.3f}" if m is not None else "—",
            f"{n:.3f}" if n is not None else "—",
        )
    console.print()
    console.print(table)

    # Monotonicity warnings.
    warnings: List[str] = []
    match_seq = [means[(q, True)] for q in QUALITY_TIERS if (q, True) in means]
    nonmatch_seq = [means[(q, False)] for q in QUALITY_TIERS if (q, False) in means]
    for i in range(len(match_seq) - 1):
        if match_seq[i] <= match_seq[i + 1]:
            warnings.append(
                f"  match scores not monotonic: {QUALITY_TIERS[i]}={match_seq[i]:.3f} "
                f"≤ {QUALITY_TIERS[i + 1]}={match_seq[i + 1]:.3f}"
            )
    for i in range(len(nonmatch_seq) - 1):
        if nonmatch_seq[i] >= nonmatch_seq[i + 1]:
            warnings.append(
                f"  non-match scores not monotonic: {QUALITY_TIERS[i]}={nonmatch_seq[i]:.3f} "
                f"≥ {QUALITY_TIERS[i + 1]}={nonmatch_seq[i + 1]:.3f}"
            )
    if warnings:
        console.print("[yellow]calibration warnings:[/yellow]")
        for w in warnings:
            console.print(f"[yellow]{w}[/yellow]")


def print_strong_failures(results: List[CaseResult], console: Console) -> None:
    """STRONG-tier failures are bugs: the labelled outcome is unambiguous
    by construction, so a wrong verdict here is a real regression.
    """
    failures = [r for r in results if r.quality == "STRONG" and r.outcome in ("FP", "FN")]
    if not failures:
        return
    failures.sort(key=lambda r: (r.outcome, -abs(r.score - r.threshold)))
    table = Table(
        title=f"STRONG-tier failures ({len(failures)}) — these should not fail",
        title_style="red",
    )
    table.add_column("group/id")
    table.add_column("schema")
    table.add_column("outcome")
    table.add_column("score", justify="right")
    table.add_column("name1")
    table.add_column("name2")
    for r in failures:
        table.add_row(
            f"{r.case_group}/{r.case_id}",
            r.schema,
            r.outcome,
            f"{r.score:.3f}",
            r.name1,
            r.name2,
        )
    console.print()
    console.print(table)


# --- CLI ---


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "-c", "--comparator",
        choices=sorted(COMPARATORS),
        help="Run named comparator over cases.csv and store the per-case result.",
    )
    mode.add_argument(
        "-s", "--summarize",
        type=Path, metavar="RUN_CSV",
        help="Summarise a previously stored per-case CSV.",
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Input cases CSV.")
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_RUN_DATA,
        help="Where to write per-case dumps in run mode.",
    )
    parser.add_argument(
        "-t", "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help="Score threshold for the predicted-match decision.",
    )
    parser.add_argument(
        "--top", type=int, default=10, help="Top-N disagreements to display.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Run mode only: skip the summary after dumping.",
    )
    parser.add_argument(
        "--frozen", action="store_true",
        help="Run mode only: write to <comparator>-frozen.csv (stable name) "
        "instead of timestamped. Use for runs you want to commit as a "
        "stable reference (e.g. logicv2-frozen.csv).",
    )
    args = parser.parse_args(argv)

    console = Console()

    if args.comparator:
        comparator = COMPARATORS[args.comparator]
        rows = load_cases(args.csv)
        results = evaluate(rows, comparator, args.threshold)
        if args.frozen:
            out_path = args.out_dir / f"{args.comparator}-frozen.csv"
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            out_path = args.out_dir / f"{args.comparator}-{timestamp}.csv"
        dump_csv(results, out_path)
        console.print(f"[bold]Comparator[/bold]: {args.comparator}")
        console.print(f"Stored {len(results)} rows in [cyan]{out_path}[/cyan]")
        console.print()
        if not args.quiet:
            print_summary(results, args.threshold, args.top, console)
    else:
        results = load_results(args.summarize, args.threshold)
        console.print(f"[bold]Source[/bold]: [cyan]{args.summarize}[/cyan]")
        console.print()
        print_summary(results, args.threshold, args.top, console)

    return 0


if __name__ == "__main__":
    sys.exit(main())
