from typing import List, Dict, Tuple
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from nomenklatura.matching.util import type_pair
from nomenklatura.util import list_intersection, names_word_list
from nomenklatura.util import soundex_token, normalize_name, jaro_winkler


def _soundex_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=normalize_name,
        processor=soundex_token,
        min_length=2,
    )


def soundex_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_tokens(n) for n in query_names_]
    result_names = [_soundex_tokens(n) for n in result_names_]
    score = 0.0
    for (q, r) in product(query_names, result_names):
        # length = max(2.0, (len(q) + len(r)) / 2.0)
        length = max(2.0, len(q))
        combo = list_intersection(q, r) / float(length)
        score = max(score, combo)
    return score


def _name_parts(name: str) -> List[str]:
    return names_word_list([name], normalizer=normalize_name)


def _align_name_parts(query: List[str], result: List[str]) -> float:
    scores: Dict[Tuple[str, str], float] = {}
    for qn, rn in product(set(query), set(result)):
        scores[(qn, rn)] = jaro_winkler(qn, rn)
    weights = []
    # length = max(2.0, (len(query) + len(result)) / 2.0)
    length = max(2.0, len(query))
    for (ln, rn), score in sorted(scores.items(), key=lambda i: i[1], reverse=True):
        while ln in query and rn in result:
            query.remove(ln)
            result.remove(rn)
            weights.append(score)
    # assume there should be at least two name parts:
    return sum(weights) / float(length)


def jaro_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_name_parts(n) for n in query_names_]
    result_names = [_name_parts(n) for n in result_names_]
    score = 0.0
    for (qn, rn) in product(query_names, result_names):
        score = max(score, _align_name_parts(qn, rn))
    return score
