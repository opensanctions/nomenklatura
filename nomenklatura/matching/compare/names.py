from typing import List, Dict, Tuple
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from nomenklatura.util import name_words, fingerprint_name, normalize_name
from nomenklatura.util import phonetic_token, soundex_token, jaro_winkler
from nomenklatura.matching.util import type_pair, props_pair, compare_sets, has_schema
from nomenklatura.matching.compare.util import is_disjoint, clean_map, has_overlap
from nomenklatura.matching.compare.util import compare_levenshtein


def _name_parts(text: str) -> List[str]:
    normalized = normalize_name(text)
    if normalized is None:
        return []
    return normalized.split(" ")


def _phonetic_name_parts(text: str) -> List[str]:
    parts: List[str] = []
    for part in _name_parts(text):
        parts.append(phonetic_token(part))
    return parts


def _soundex_name_parts(text: str) -> List[str]:
    parts: List[str] = []
    for part in _name_parts(text):
        parts.append(soundex_token(part))
    return parts


def _count_overlap(query: List[str], result: List[str]) -> int:
    overlap = 0
    remainder = list(result)
    for q in query:
        if q in remainder:
            overlap += 1
            remainder.remove(q)
    return overlap


def person_name_phonetic_match(query: E, result: E) -> float:
    """Two persons have similar names, using a phonetic algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_phonetic_name_parts(n) for n in query_names_]
    result_names = [_phonetic_name_parts(n) for n in result_names_]
    score = 0.0
    for (q, r) in product(query_names, result_names):
        length = min(len(q), len(r))
        combo = _count_overlap(q, r) / float(length)
        score = max(score, combo)
    return score


def soundex_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_name_parts(n) for n in query_names_]
    result_names = [_soundex_name_parts(n) for n in result_names_]
    score = 0.0
    for (q, r) in product(query_names, result_names):
        length = min(len(q), len(r))
        combo = _count_overlap(q, r) / float(length)
        score = max(score, combo)
    return score


def _align_name_parts(left: List[str], right: List[str]) -> float:
    scores: Dict[Tuple[str, str], float] = {}
    for ln, rn in product(set(left), set(right)):
        scores[(ln, rn)] = jaro_winkler(ln, rn)
    weights = []
    shortest = min(len(left), len(right))
    for (ln, rn), score in sorted(scores.items(), key=lambda i: i[1], reverse=True):
        while ln in left and rn in right:
            left.remove(ln)
            right.remove(rn)
            weights.append(score)
    # assume there should be at least two name parts:
    return sum(weights) / float(max(2.0, shortest))


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


def person_name_jaro_winkler(query: E, result: E) -> float:
    """Compare two persons' names using the Jaro-Winkler string similarity algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    return jaro_name_parts(query, result)


def name_literal_match(query: E, result: E) -> float:
    """Two entities have the same name, without normalization applied to the name."""
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, lambda s: s.lower())
    rnames = clean_map(result_names, lambda s: s.lower())
    return 1.0 if has_overlap(qnames, rnames) else 0.0


def name_fingerprint_levenshtein(query: E, result: E) -> float:
    """Two non-person entities have similar fingerprinted names. This includes
    simplifying entity type names (e.g. "Limited" -> "Ltd")."""
    if has_schema(query, result, "Person"):
        return 0.0
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, fingerprint_name)
    rnames = clean_map(result_names, fingerprint_name)
    return compare_sets(qnames, rnames, compare_levenshtein)


def last_name_mismatch(left: E, right: E) -> float:
    """The two persons have different last names."""
    lv, rv = props_pair(left, right, ["lastName"])
    lvt = name_words(lv)
    rvt = name_words(rv)
    return 1.0 if is_disjoint(lvt, rvt) else 0.0
