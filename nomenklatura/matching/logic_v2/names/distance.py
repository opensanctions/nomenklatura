from functools import lru_cache
from typing import List

from rigour.names import Alignment, NamePart, compare_parts
from rigour.text import levenshtein

from nomenklatura.matching.types import ScoringConfig
from nomenklatura.matching.util import MEMO_BATCH


@lru_cache(maxsize=MEMO_BATCH)
def strict_levenshtein(left: str, right: str, max_rate: int = 4) -> float:
    """Calculate the string distance between two strings."""
    if left == right:
        return 1.0
    max_len = max(len(left), len(right))
    max_edits = max_len // max_rate
    if max_edits < 1:  # We already checked for equality
        return 0.0
    distance = levenshtein(left, right, max_edits=max_len)
    if distance > max_edits:
        return 0.0
    return (1 - (distance / max_len)) ** max_edits


def weighted_edit_similarity(
    qry_parts: List[NamePart], res_parts: List[NamePart], config: ScoringConfig
) -> List[Alignment]:
    """Score the residue alignment of two name-part lists.

    Thin wrapper over `rigour.names.compare_parts`, which is the
    Rust-backed cost-folded Wagner-Fischer + 0.51-overlap clustering
    + product-of-side-similarities scoring. Returns one
    `Alignment` per cluster (paired or solo). Every input part
    appears in exactly one cluster's `qps` / `rps`. Returned
    alignments carry `symbol = None` and a per-cluster
    fuzzy-distance score; the matcher applies weight policy
    (extras, stopword, family-name) on top.
    """
    return compare_parts(
        qry_parts,
        res_parts,
        fuzzy_tolerance=config.get_float("nm_fuzzy_cutoff_factor"),
    )
