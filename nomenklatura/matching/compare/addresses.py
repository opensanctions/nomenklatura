from functools import lru_cache
from typing import Set
from followthemoney.proxy import E
from followthemoney.types import registry
from itertools import product
from rigour.text import levenshtein_similarity
from rigour.addresses import normalize_address, remove_address_keywords

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import FNUL, MEMO_BATCH, has_schema


@lru_cache(maxsize=MEMO_BATCH)
def _normalize_address(addr: str) -> Set[str]:
    """Normalize an address string into tokens."""
    norm = normalize_address(addr, latinize=True)
    if norm is None:
        return set()
    norm = remove_address_keywords(norm, latinize=True)
    if norm is None:
        return set()
    return set([n for n in norm.split() if len(n) > 0])


def _address_match(query: E, result: E) -> FtResult:
    """Text similarity between addresses."""
    query_addrs = query.get_type_values(registry.address, matchable=True)
    result_addrs = result.get_type_values(registry.address, matchable=True)
    if len(query_addrs) == 0 or len(result_addrs) == 0:
        return FtResult(score=FNUL, detail=None)
    max_result = FtResult(score=FNUL, detail=None)
    query_norms = [_normalize_address(addr) for addr in query_addrs]
    result_norms = [_normalize_address(addr) for addr in result_addrs]
    for query_tokens, result_tokens in product(query_norms, result_norms):
        if len(query_tokens) == 0 or len(result_tokens) == 0:
            continue
        # pick out tokens that are in both sets and treat those as safe gains
        overlap = query_tokens.intersection(result_tokens)
        if len(overlap) == len(query_tokens) or len(overlap) == len(result_tokens):
            detail = f"Address matches subset: {' '.join(overlap)}"
            return FtResult(score=1.0, detail=detail)

        # sort the address tokens alphabetically to address different orderings
        query_rem = sorted([t for t in query_tokens if t not in overlap])
        query_fuzzy = " ".join(query_rem)
        result_rem = sorted([t for t in result_tokens if t not in overlap])
        result_fuzzy = " ".join(result_rem)
        fuzzy_len = max(len(query_fuzzy), len(result_fuzzy))
        score = levenshtein_similarity(query_fuzzy, result_fuzzy, max_edits=fuzzy_len)

        # combine the scores from overlap and levenshtein
        rem_len = max(len(query_rem), len(result_rem))
        score = (len(overlap) + (rem_len * (score))) / (rem_len + len(overlap))
        if score > max_result.score:
            detail = f"Matched addresses: {query_fuzzy} <-> {result_fuzzy}"
            max_result = FtResult(score=score, detail=detail)
    return max_result


def address_entity_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two address entities relate to similar addresses."""
    if not has_schema(query, result, "Address"):
        return FtResult(score=FNUL, detail=None)
    return _address_match(query, result)


def address_prop_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Two entities have similar stated addresses."""
    if has_schema(query, result, "Address"):
        return FtResult(score=FNUL, detail=None)
    return _address_match(query, result)
