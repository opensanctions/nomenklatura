from functools import lru_cache
import math
from collections import defaultdict
from itertools import zip_longest, chain
from typing import Dict, List, Optional, Tuple
from rapidfuzz.distance import Levenshtein, Opcodes
from rigour.names import NamePart, is_stopword
from rigour.text.distance import levenshtein
from nomenklatura.matching.logic_v2.names.magic import PART_WEIGHTS
from nomenklatura.matching.logic_v2.names.util import Match

SEP = " "
SIMILAR_PAIRS = [
    ("0", "o"),
    ("1", "i"),
    ("g", "9"),
    ("e", "i"),
    ("1", "l"),
    ("o", "u"),
    ("i", "j"),
    ("c", "k"),
]
SIMILAR_PAIRS = SIMILAR_PAIRS + [(b, a) for a, b in SIMILAR_PAIRS]


@lru_cache(maxsize=512)
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


def _part_weight(part: NamePart, base: float) -> float:
    """Calculate the weight of a name part based on its tag."""
    if part.tag in PART_WEIGHTS:
        return base * PART_WEIGHTS[part.tag]
    if is_stopword(part.form):
        return base * 0.7
    return base


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


def _costs_similarity(costs: List[float]) -> float:
    """Calculate a similarity score based on a list of costs."""
    if len(costs) == 0:
        return 0.0
    max_cost = math.log(max(len(costs) - 2, 1))
    total_cost = sum(costs)
    if total_cost == 0:
        return 1.0
    if total_cost > max_cost:
        return 0.0
    # Normalize the score to be between 0 and 1
    return 1 - (total_cost / len(costs))


@lru_cache(maxsize=512)
def _opcodes(qry_text: str, res_text: str) -> Opcodes:
    """Get the opcodes for the Levenshtein distance between two strings."""
    return Levenshtein.opcodes(qry_text, res_text)


def weighted_edit_similarity(
    qry_parts: List[NamePart],
    res_parts: List[NamePart],
    extra_query_part_weight: float = 0.8,
    extra_result_part_weight: float = 0.1,
) -> List[Match]:
    """Calculate a weighted similarity score between two sets of name parts. This function implements custom
    frills within the context of a simple Levenshtein distance calculation. For example:

    * The result is returned as a list of Match objects, which contain a score, but also a weight.
    * Removals of full tokens are penalized more lightly than intra-token edits.
    * Some edits inside of words are considered more similar than others, e.g. "o" and "0".
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
                        next_idx = qry_parts.index(qry_cur) + 1
                        if len(qry_parts) >= next_idx:
                            qry_cur = qry_parts[next_idx]
                if rc is not None:
                    costs[res_cur].append(cost)
                    if rc == SEP:
                        next_idx = res_parts.index(res_cur) + 1
                        if len(res_parts) >= next_idx:
                            res_cur = res_parts[next_idx]

    # Use the overlaps to create matches between query and result parts.
    matches: Dict[NamePart, Match] = {}
    for (qp, rp), overlap in overlaps.items():
        min_len = min(len(qp.comparable), len(rp.comparable))
        if overlap / min_len > 0.51:
            match = matches.get(qp, matches.get(rp, Match()))
            if qp not in match.qps:
                match.qps.append(qp)
            if rp not in match.rps:
                match.rps.append(rp)
            qcosts = list(chain.from_iterable(costs.get(p, [1.0]) for p in match.qps))
            rcosts = list(chain.from_iterable(costs.get(p, [1.0]) for p in match.rps))
            # TODO: multiply?
            match.score = _costs_similarity(qcosts) * _costs_similarity(rcosts)
            if len(match.qps) == 1 and len(match.rps) == 1:
                if is_stopword(qp.form):
                    match.weight = 0.7
            matches[rp] = match
            matches[qp] = match

    # Non-matched query parts: this penalizes scenarios where name parts in the query are
    # not matched to any name part in the result. Increasing this penalty will require queries
    # to always be matched in full.
    for qp in qry_parts:
        if qp not in matches:
            match = Match(qps=[qp])
            match.weight = _part_weight(qp, extra_query_part_weight)
            matches[qp] = match

    # Non-matched result parts
    for rp in res_parts:
        if rp not in matches:
            match = Match(rps=[rp])
            match.weight = _part_weight(rp, extra_result_part_weight)
            matches[rp] = match

    return list(set(matches.values()))
