from typing import List, Dict, Tuple
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from fingerprints import clean_name_light, clean_name_ascii
from nomenklatura.util import names_word_list, levenshtein, levenshtein_similarity
from nomenklatura.util import fingerprint_name, normalize_name, jaro_winkler
from nomenklatura.matching.util import type_pair, props_pair, has_schema
from nomenklatura.matching.compare.util import is_disjoint, clean_map, has_overlap


def _name_parts(name: str) -> List[str]:
    return names_word_list([name], normalizer=normalize_name)


def _is_levenshtein_plausible(query: str, result: str) -> bool:
    # Skip results with an overall distance of more than 3 characters:
    max_edits = min(3, (min(len(query), len(result)) // 3))
    return levenshtein(query, result) <= max_edits


def _align_name_parts(query: List[str], result: List[str]) -> float:
    if len(query) == 0 or len(result) == 0:
        return 0.0
    scores: Dict[Tuple[str, str], float] = {}
    # compute all pairwise scores for name parts:
    for qn, rn in product(set(query), set(result)):
        score = jaro_winkler(qn, rn)
        if score > 0.0 and _is_levenshtein_plausible(qn, rn):
            scores[(qn, rn)] = score
    pairs: List[Tuple[str, str]] = []
    # original length of query:
    length = len(query)
    total_score = 1.0
    # find the best pairing for each name part by score:
    for (qn, rn), score in sorted(scores.items(), key=lambda i: i[1], reverse=True):
        # one name part can only be used once, but can show up multiple times:
        while qn in query and rn in result:
            query.remove(qn)
            result.remove(rn)
            total_score = total_score * score
            pairs.append((qn, rn))
    # assume there should be at least a candidate for each query name part:
    if len(pairs) < length:
        return 0.0
    # weakest evidence first to bias jaro-winkler for lower scores on imperfect matches:
    aligned = pairs[::-1]
    query_aligned = " ".join(p[0] for p in aligned)
    result_aligned = " ".join(p[1] for p in aligned)
    if not _is_levenshtein_plausible(query_aligned, result_aligned):
        return 0.0
    # return an amped-up jaro-winkler score for the aligned name parts:
    return total_score
    # return jaro_winkler(query_aligned, result_aligned)


def person_name_jaro_winkler(query: E, result: E) -> float:
    """Compare two persons' names using the Jaro-Winkler string similarity algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_name_parts(n) for n in query_names_]
    result_names = [_name_parts(n) for n in result_names_]
    score = 0.0
    for (qn, rn) in product(query_names, result_names):
        score = max(score, _align_name_parts(list(qn), list(rn)))
    return score


def name_literal_match(query: E, result: E) -> float:
    """Two entities have the same name, without normalization applied to the name."""
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, clean_name_light)
    rnames = clean_map(result_names, clean_name_light)
    return 1.0 if has_overlap(qnames, rnames) else 0.0


def _fp_name_parts(name: str) -> List[str]:
    return names_word_list([name], normalizer=fingerprint_name, min_length=2)


def _fpw_name_parts(name: str) -> List[str]:
    parts = names_word_list([name], normalizer=fingerprint_name, min_length=2)
    for part in names_word_list([name], normalizer=clean_name_ascii, min_length=2):
        if part not in parts:
            parts.append(part)
    return parts


def name_fingerprint_levenshtein(query: E, result: E) -> float:
    """Two non-person entities have similar fingerprinted names. This includes
    simplifying entity type names (e.g. "Limited" -> "Ltd") and uses the
    Damerau-Levensthein string distance algorithm."""
    if has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_fp_name_parts(n) for n in query_names_]
    result_names = [_fpw_name_parts(n) for n in result_names_]
    max_score = 0.0
    for (qn, rn) in product(query_names, result_names):
        if len(qn) == 0:
            continue
        scores: Dict[Tuple[str, str], float] = {}
        # compute all pairwise scores for name parts:
        for q, r in product(set(qn), set(rn)):
            scores[(q, r)] = levenshtein_similarity(q, r)
        aligned: List[Tuple[str, str, float]] = []
        # find the best pairing for each name part by score:
        for (q, r), score in sorted(scores.items(), key=lambda i: i[1], reverse=True):
            # one name part can only be used once, but can show up multiple times:
            while q in qn and r in rn:
                qn.remove(q)
                rn.remove(r)
                aligned.append((q, r, score))
        # assume there should be at least a candidate for each query name part:
        if len(qn):
            continue
        qaligned = " ".join(p[0] for p in aligned)
        raligned = " ".join(p[1] for p in aligned)
        distance = levenshtein(qaligned, raligned)
        # Skip results with an overall distance of more than 5 characters:
        max_edits = min(4, (min(len(qaligned), len(raligned)) // 3))
        if distance > max_edits:
            continue
        score = levenshtein_similarity(qaligned, raligned, distance)
        max_score = max(max_score, score)
    return max_score


def last_name_mismatch(query: E, result: E) -> float:
    """The two persons have different last names."""
    qv, rv = props_pair(query, result, ["lastName"])
    qvt = names_word_list(qv, min_length=2)
    rvt = names_word_list(rv, min_length=2)
    return 1.0 if is_disjoint(qvt, rvt) else 0.0


def weak_alias_match(query: E, result: E) -> float:
    """The query name is exactly the same as a result's weak alias."""
    # NOTE: This is unbalanced, i.e. it treats 'query' and 'result' differently.
    # cf. https://ofac.treasury.gov/faqs/topic/1646
    query_names = query.get_type_values(registry.name)
    query_names.extend(query.get("weakAlias", quiet=True))
    result_names = result.get("weakAlias", quiet=True)
    qnames = clean_map(query_names, clean_name_light)
    rnames = clean_map(result_names, clean_name_light)
    return 1.0 if has_overlap(qnames, rnames) else 0.0
