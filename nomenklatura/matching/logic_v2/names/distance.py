import math
from functools import lru_cache
from collections import defaultdict
from itertools import zip_longest
from typing import Dict, List, Optional, Tuple
from rapidfuzz.distance import Levenshtein, Opcodes
from rigour.names import Alignment, NamePart
from rigour.text import levenshtein

from nomenklatura.matching.types import ScoringConfig
from nomenklatura.matching.util import MEMO_BATCH
from nomenklatura.util import unroll


class _PartCluster:
    """Internal mutable scaffold used during 0.51-overlap cluster
    assembly. Converted to a frozen `Alignment` at function exit.
    Object identity is the dedup key (set-via-id) — clusters are
    distinct holders, not values."""

    __slots__ = ("qps", "rps", "score")

    def __init__(self) -> None:
        self.qps: List[NamePart] = []
        self.rps: List[NamePart] = []
        self.score: float = 0.0

SEP = " "
SIMILAR_PAIRS = [
    ("0", "o"),
    ("1", "i"),
    ("g", "9"),
    ("q", "9"),
    ("b", "6"),
    ("5", "s"),
    ("e", "i"),
    ("1", "l"),
    ("o", "u"),
    ("i", "j"),
    ("i", "y"),
    ("c", "k"),
    ("n", "h"),
]
SIMILAR_PAIRS = SIMILAR_PAIRS + [(b, a) for a, b in SIMILAR_PAIRS]


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


def _edit_cost(op: str, qc: Optional[str], rc: Optional[str]) -> float:
    """Calculate the cost of a pair of characters."""
    if op == "equal":
        return 0.0
    if qc == SEP and rc is None:
        return 0.2
    if rc == SEP and qc is None:
        return 0.2
    if (qc, rc) in SIMILAR_PAIRS:
        return 0.7
    if qc is not None and qc.isdigit():
        return 1.5
    if rc is not None and rc.isdigit():
        return 1.5
    return 1.0


def _costs_similarity(costs: List[float], max_cost_bias: float = 1.0) -> float:
    """Calculate a similarity score based on a list of costs."""
    if len(costs) == 0:
        return 0.0
    # max_cost defines how many edits we allow for a given length.
    # We use a log here because for very long names, we don't want an anything goes
    # policy for very long name strings (~hundreds of characters).
    # The log-base is a bit of a magic number. We adjusted it so that for
    # len 8 it allows ~2 edits. That seems reasonable, but is also entirely arbitrary.
    # We use log(x-2) to disable fuzzy-matching completely for very short
    # names (often Chinese names in practice).
    max_cost = math.log(max(len(costs) - 2, 1), 2.35) * max_cost_bias
    total_cost = sum(costs)
    if total_cost == 0:
        return 1.0
    if total_cost > max_cost:
        return 0.0
    # Normalize the score to be between 0 and 1
    return 1 - (total_cost / len(costs))


# @lru_cache(maxsize=MEMO_BATCH)
def _opcodes(qry_text: str, res_text: str) -> Opcodes:
    """Get the opcodes for the Levenshtein distance between two strings."""
    return Levenshtein.opcodes(qry_text, res_text)


def weighted_edit_similarity(
    qry_parts: List[NamePart], res_parts: List[NamePart], config: ScoringConfig
) -> List[Alignment]:
    """Score the residue alignment of two name-part lists.

    Returns one [Alignment][rigour.names.Alignment] per cluster
    (paired or solo). Every input part appears in exactly one
    cluster's `qps` / `rps`. Returned alignments carry
    `symbol = None` and a per-cluster fuzzy-distance score; the
    matcher applies weight policy (extras, stopword, family-name)
    on top.

    * Removals of full tokens are penalised more lightly than
      intra-token edits.
    * Some edits inside of words are considered more similar than
      others, e.g. "o" and "0".
    """
    if len(qry_parts) == 0 and len(res_parts) == 0:
        return []
    qry_text = SEP.join(p.comparable for p in qry_parts)
    res_text = SEP.join(p.comparable for p in res_parts)

    # Keep track of which name parts overlap and how many characters they share in the alignment
    # produced by rapidfuzz Levenshtein opcodes.
    overlaps: Dict[Tuple[NamePart, NamePart], int] = defaultdict(int)

    # Keep track of the costs for each name part, so we can calculate a similarity score later.
    costs: Dict[NamePart, List[float]] = defaultdict(list)

    if len(qry_parts) and len(res_parts):
        qry_idx = 0
        res_idx = 0
        qry_cur = qry_parts[0]
        res_cur = res_parts[0]
        for op in _opcodes(qry_text, res_text):
            qry_span = qry_text[op.src_start : op.src_end]
            res_span = res_text[op.dest_start : op.dest_end]
            for qc, rc in zip_longest(qry_span, res_span, fillvalue=None):
                if op.tag == "equal":
                    if qc not in (None, SEP) and rc not in (None, SEP):
                        # TODO: should this also include "replace"?
                        overlaps[(qry_cur, res_cur)] += 1
                cost = _edit_cost(op.tag, qc, rc)
                if qc is not None:
                    costs[qry_cur].append(cost)
                    if qc == SEP:
                        qry_idx += 1
                        if qry_idx < len(qry_parts):
                            qry_cur = qry_parts[qry_idx]
                if rc is not None:
                    costs[res_cur].append(cost)
                    if rc == SEP:
                        res_idx += 1
                        if res_idx < len(res_parts):
                            res_cur = res_parts[res_idx]

    # Use the overlaps to create clusters between query and result parts.
    part_clusters: Dict[NamePart, _PartCluster] = {}
    for (qp, rp), overlap in overlaps.items():
        min_len = min(len(qp.comparable), len(rp.comparable))
        if overlap / min_len > 0.51:
            cluster = part_clusters.get(qp, part_clusters.get(rp, _PartCluster()))
            if qp not in cluster.qps:
                cluster.qps.append(qp)
            if rp not in cluster.rps:
                cluster.rps.append(rp)
            part_clusters[rp] = cluster
            part_clusters[qp] = cluster

    # Dedupe by object identity — distinct cluster instances are distinct outputs even if
    # their part lists later collide; same instance shared across multiple key entries
    # collapses to one. set() works: _PartCluster has no __eq__/__hash__ overrides so it
    # uses default id-based identity.
    clusters: List[_PartCluster] = list(set(part_clusters.values()))

    # Compute the scores where an overlap was applied
    bias = config.get_float("nm_fuzzy_cutoff_factor")
    for cluster in clusters:
        qcosts = unroll(costs.get(p, [1.0]) for p in cluster.qps)
        rcosts = unroll(costs.get(p, [1.0]) for p in cluster.rps)
        cluster.score = _costs_similarity(
            qcosts, max_cost_bias=bias
        ) * _costs_similarity(rcosts, max_cost_bias=bias)

    # Non-matched query parts: this penalizes scenarios where name parts in the query are
    # not matched to any name part in the result. Increasing this penalty will require queries
    # to always be matched in full.
    for qp in qry_parts:
        if qp not in part_clusters:
            solo = _PartCluster()
            solo.qps = [qp]
            clusters.append(solo)

    # Non-matched result parts
    for rp in res_parts:
        if rp not in part_clusters:
            solo = _PartCluster()
            solo.rps = [rp]
            clusters.append(solo)

    return [
        Alignment(qps=c.qps, rps=c.rps, symbol=None, score=c.score) for c in clusters
    ]
