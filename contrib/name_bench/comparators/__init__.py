"""Comparator registry for the name-distance harness.

A `Comparator` is a callable `(name1, name2, schema) -> float`
that returns a similarity score in `[0, 1]`. Each comparator
chooses its own pre-processing — analyze_names, pair_symbols,
tag_sort, or just raw string distance.

Add an iteration: drop a new module under `comparators/`
defining the function, import it here, register it in
`COMPARATORS` under a unique name. The CLI's `-c` flag picks
from `COMPARATORS.keys()`.
"""

from __future__ import annotations

from typing import Callable, Dict

from .levenshtein import levenshtein_baseline
from .logicv2 import logicv2_baseline


Comparator = Callable[[str, str, str], float]


COMPARATORS: Dict[str, Comparator] = {
    "levenshtein": levenshtein_baseline,
    "logicv2": logicv2_baseline,
}


__all__ = ["COMPARATORS", "Comparator"]
