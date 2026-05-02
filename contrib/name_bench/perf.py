"""Perf harness: time each comparator across N runs of cases.csv.

Apples-to-apples scoreboard combining accuracy (F1, precision, recall)
with timing (mean / p50 / p95 / total μs per call). Plus a leaderboard
of the slowest cases per comparator (top N% by per-case median time)
for investigation — these are typically long ORG names or pairs whose
alignment matrix is large.

Usage:

    python contrib/name_comparison/perf.py
    python contrib/name_comparison/perf.py --runs 100
    python contrib/name_comparison/perf.py -c logicv2 -c levenshtein
    python contrib/name_comparison/perf.py --top-slow-pct 10
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Reuse run.py's loader so case_id computation stays in one place.
sys.path.insert(0, str(Path(__file__).parent))
from run import load_cases  # noqa: E402

from rich.console import Console
from rich.table import Table

# Local comparators package import.
sys.path.insert(0, str(Path(__file__).parent))
from comparators import COMPARATORS  # noqa: E402


HERE = Path(__file__).parent
DEFAULT_CASES = HERE / "cases.csv"
DEFAULT_RUNS = 10
DEFAULT_THRESHOLD = 0.7
DEFAULT_TOP_SLOW_PCT = 5.0


CaseKey = Tuple[str, str]


def time_comparator(
    comparator, rows: List[Dict[str, str]], runs: int
) -> Tuple[Dict[CaseKey, List[float]], Dict[CaseKey, float]]:
    """Time each case `runs` times. Returns per-case μs samples + last-run score.

    A single warmup pass is done before timing to absorb first-call import
    / cache effects (PyO3 type lookup, lazy data loading, etc.).
    """
    # Warmup
    for row in rows:
        comparator(row["name1"], row["name2"], row["schema"])

    samples: Dict[CaseKey, List[float]] = defaultdict(list)
    score: Dict[CaseKey, float] = {}
    for _ in range(runs):
        for row in rows:
            key: CaseKey = (row["case_group"], row["case_id"])
            t0 = time.perf_counter_ns()
            s = comparator(row["name1"], row["name2"], row["schema"])
            t1 = time.perf_counter_ns()
            samples[key].append((t1 - t0) / 1000.0)
            score[key] = s
    return samples, score


def compute_metrics(
    rows: List[Dict[str, str]],
    score: Dict[CaseKey, float],
    threshold: float,
) -> Dict[str, float]:
    tp = fp = tn = fn = 0
    for row in rows:
        key = (row["case_group"], row["case_id"])
        is_match = row["is_match"].lower() == "true"
        predicted = score[key] >= threshold
        if is_match and predicted:
            tp += 1
        elif is_match:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": p, "recall": r, "f1": f1}


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * pct / 100), len(s) - 1)
    return s[idx]


def render_scoreboard(results: Dict[str, dict], console: Console) -> None:
    table = Table(title="Comparator scoreboard (accuracy + timing)")
    table.add_column("comparator")
    table.add_column("F1", justify="right", style="cyan")
    table.add_column("P", justify="right")
    table.add_column("R", justify="right")
    table.add_column("μs mean", justify="right", style="yellow")
    table.add_column("μs p50", justify="right")
    table.add_column("μs p95", justify="right")
    table.add_column("total ms", justify="right")
    for name, res in results.items():
        m = res["metrics"]
        table.add_row(
            name,
            f"{m['f1']:.3f}",
            f"{m['precision']:.3f}",
            f"{m['recall']:.3f}",
            f"{res['mean_us']:.1f}",
            f"{res['p50_us']:.1f}",
            f"{res['p95_us']:.1f}",
            f"{res['total_us'] / 1000.0:.1f}",
        )
    console.print(table)


def render_slow_cases(
    name: str,
    medians: Dict[CaseKey, float],
    rows_by_key: Dict[CaseKey, Dict[str, str]],
    n: int,
    console: Console,
) -> None:
    sorted_cases = sorted(medians.items(), key=lambda x: -x[1])[:n]
    table = Table(title=f"Top {n} slowest cases — {name}")
    table.add_column("group/id")
    table.add_column("schema")
    table.add_column("μs (median)", justify="right")
    table.add_column("name1")
    table.add_column("name2")
    for key, us in sorted_cases:
        row = rows_by_key[key]
        table.add_row(
            f"{key[0]}/{key[1]}",
            row["schema"],
            f"{us:.1f}",
            row["name1"],
            row["name2"],
        )
    console.print(table)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"Number of runs per case (default {DEFAULT_RUNS}).")
    parser.add_argument("-t", "--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("-c", "--comparator", action="append",
                        choices=sorted(COMPARATORS.keys()),
                        help="Run only the named comparator(s); default = all.")
    parser.add_argument("--top-slow-pct", type=float, default=DEFAULT_TOP_SLOW_PCT,
                        help=f"Report top N%% slowest cases per comparator "
                             f"(default {DEFAULT_TOP_SLOW_PCT}%%).")
    args = parser.parse_args(argv)

    rows = load_cases(args.cases)
    rows_by_key: Dict[CaseKey, Dict[str, str]] = {
        (r["case_group"], r["case_id"]): r for r in rows
    }
    chosen = args.comparator if args.comparator else sorted(COMPARATORS.keys())

    console = Console()
    console.print(
        f"[bold]Cases[/bold]: {len(rows)}    "
        f"[bold]Runs[/bold]: {args.runs}    "
        f"[bold]Threshold[/bold]: {args.threshold}"
    )
    console.print()

    results: Dict[str, dict] = {}
    for name in chosen:
        console.print(f"[dim]Running {name}…[/dim]")
        comparator = COMPARATORS[name]
        samples, score = time_comparator(comparator, rows, args.runs)
        metrics = compute_metrics(rows, score, args.threshold)
        medians = {k: statistics.median(v) for k, v in samples.items()}
        all_med = list(medians.values())
        results[name] = {
            "metrics": metrics,
            "medians": medians,
            "mean_us": statistics.mean(all_med),
            "p50_us": percentile(all_med, 50),
            "p95_us": percentile(all_med, 95),
            "total_us": sum(all_med),
        }

    console.print()
    render_scoreboard(results, console)

    n_slow = max(1, int(len(rows) * args.top_slow_pct / 100))
    for name, res in results.items():
        console.print()
        render_slow_cases(name, res["medians"], rows_by_key, n_slow, console)

    return 0


if __name__ == "__main__":
    sys.exit(main())
