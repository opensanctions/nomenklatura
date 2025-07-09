import math
import itertools
from typing import List, Optional, Tuple
from rapidfuzz.distance import Levenshtein
from rigour.names import NamePart, NamePartTag
from rigour.text.distance import dam_levenshtein, levenshtein

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


def levenshtein_similarity(query: str, result: str) -> float:
    if len(query) == 0 or len(result) == 0:
        return 0.0
    if query == result:
        return 1.0
    max_len = max(len(query), len(result))
    max_edits = math.floor(math.log(max(max_len - 2, 1)))
    if max_edits < 1:
        return 0.0
    distance = dam_levenshtein(query, result, max_edits=max_edits)
    if distance > max_edits:
        return 0.0
    score = 1 - (distance / max_len)
    score = score**2
    if score < 0.5:
        score = 0.0
    return score


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


def edit_cost(op: str, qc: Optional[str], rc: Optional[str]) -> float:
    """Calculate the cost of a pair of characters."""
    if op == "equal":
        return 0.0
    if qc == SEP and rc is None:
        return 0.2
    if rc == SEP and qc is None:
        return 0.2
    if (qc, rc) in SIMILAR_PAIRS:
        return 0.6
    if qc is not None and qc.isdigit():
        return 1.5
    if rc is not None and rc.isdigit():
        return 1.5
    return 1.0


def costs_similarity(costs: List[float], default: float = 0.0) -> float:
    """Calculate a similarity score based on a list of costs."""
    if len(costs) == 0:
        return 0.0
    max_cost = math.log(max(len(costs) - 2, 1))
    total_cost = sum(costs)
    if total_cost == 0:
        return 1.0
    if total_cost > max_cost:
        return default
    # Normalize the score to be between 0 and 1
    return 1 - (total_cost / len(costs))


def weighted_edit_similarity(
    qry_parts: List[NamePart],
    res_parts: List[NamePart],
) -> List[float]:
    """Calculate a weighted similarity score between two sets of name parts."""
    if len(qry_parts) == 0 and len(res_parts) == 0:
        return []
    qry_text = SEP.join(p.comparable for p in qry_parts)
    res_text = SEP.join(p.comparable for p in res_parts)

    qry_costs: List[Tuple[NamePart, List[float]]] = []
    res_costs: List[Tuple[NamePart, List[float]]] = []
    if len(qry_parts) == 0:
        res_costs = [(p, [1.0]) for p in res_parts]
    elif len(res_parts) == 0:
        qry_costs = [(p, [1.0]) for p in qry_parts]
    else:
        qry_costs.append((qry_parts[0], []))
        res_costs.append((res_parts[0], []))
        for op in Levenshtein.opcodes(qry_text, res_text):
            qry_span = qry_text[op.src_start : op.src_end]
            res_span = res_text[op.dest_start : op.dest_end]
            for qc, rc in itertools.zip_longest(qry_span, res_span, fillvalue=None):
                cost = edit_cost(op.tag, qc, rc)
                if qc is not None:
                    qry_costs[-1][1].append(cost)
                    if qc == SEP:
                        if len(qry_parts) > len(qry_costs):
                            qry_costs.append((qry_parts[len(qry_costs)], []))
                if rc is not None:
                    res_costs[-1][1].append(cost)
                    if rc == SEP:
                        if len(res_parts) > len(res_costs):
                            res_costs.append((res_parts[len(res_costs)], []))

    weights: List[float] = []
    for qp, costs in qry_costs:
        similarity = costs_similarity(costs)
        weights.append(similarity)

    for rp, costs in res_costs:
        similarity = costs_similarity(costs)
        weights.append(similarity)
    return weights
