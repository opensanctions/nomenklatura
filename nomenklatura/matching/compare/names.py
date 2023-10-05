from typing import List, Dict, Tuple
from itertools import product
from followthemoney.proxy import E
from followthemoney.types import registry
from fingerprints.cleanup import clean_name_light
from nomenklatura.util import names_word_list, list_intersection
from nomenklatura.util import fingerprint_name, normalize_name, jaro_winkler
from nomenklatura.util import phonetic_token, metaphone_token, soundex_token
from nomenklatura.util import levenshtein
from nomenklatura.matching.util import type_pair, props_pair, compare_sets, has_schema
from nomenklatura.matching.compare.util import is_disjoint, clean_map, has_overlap
from nomenklatura.matching.compare.util import compare_levenshtein


def _phonetic_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=normalize_name,
        processor=phonetic_token,
        min_length=2,
    )


def _token_names_compare(
    query_names: List[List[str]], result_names: List[List[str]]
) -> float:
    score = 0.0
    for (q, r) in product(query_names, result_names):
        # length = max(2.0, (len(q) + len(r)) / 2.0)
        length = max(2.0, len(q))
        combo = list_intersection(q, r) / float(length)
        score = max(score, combo)
    return score


def person_name_phonetic_match(query: E, result: E) -> float:
    """Two persons have similar names, using a phonetic algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_phonetic_tokens(n) for n in query_names_]
    result_names = [_phonetic_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _metaphone_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=fingerprint_name,
        processor=metaphone_token,
        min_length=2,
    )


def name_metaphone_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the metaphone
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_metaphone_tokens(n) for n in query_names_]
    result_names = [_metaphone_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _soundex_tokens(token: str) -> List[str]:
    return names_word_list(
        [token],
        normalizer=fingerprint_name,
        processor=soundex_token,
        min_length=2,
    )


def name_soundex_match(query: E, result: E) -> float:
    """Two entities (person and non-person) have similar names, using the soundex
    algorithm."""
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_soundex_tokens(n) for n in query_names_]
    result_names = [_soundex_tokens(n) for n in result_names_]
    return _token_names_compare(query_names, result_names)


def _name_parts(name: str) -> List[str]:
    return names_word_list([name], normalizer=normalize_name)


def _align_name_parts(query: List[str], result: List[str]) -> float:
    scores: Dict[Tuple[str, str], float] = {}
    # compute all pairwise scores for name parts:
    for qn, rn in product(set(query), set(result)):
        scores[(qn, rn)] = jaro_winkler(qn, rn)
    pairs: List[Tuple[str, str]] = []
    # original length of query:
    length = len(query)
    # find the best pairing for each name part by score:
    for (qn, rn), score in sorted(scores.items(), key=lambda i: i[1], reverse=True):
        if score == 0.0:
            break
        # one name part can only be used once, but can show up multiple times:
        while qn in query and rn in result:
            query.remove(qn)
            result.remove(rn)
            pairs.append((qn, rn))
    # assume there should be at least two name parts:
    if len(pairs) < length:
        return 0.0
    # weakest evidence first to bias jaro-winkler for lower scores on imperfect matches:
    aligned = pairs[::-1]
    query_aligned = " ".join(p[0] for p in aligned)
    result_aligned = " ".join(p[1] for p in aligned)
    # Skip results with an overall distance of more than 3 characters:
    max_edits = min(3, (min(len(query_aligned), len(result_aligned)) // 3))
    if levenshtein(query_aligned, result_aligned) > max_edits:
        return 0.0
    # return an amped-up jaro-winkler score for the aligned name parts:
    return jaro_winkler(query_aligned, result_aligned)


def person_name_jaro_winkler(query: E, result: E) -> float:
    """Compare two persons' names using the Jaro-Winkler string similarity algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names_, result_names_ = type_pair(query, result, registry.name)
    query_names = [_name_parts(n) for n in query_names_]
    result_names = [_name_parts(n) for n in result_names_]
    score = 0.0
    for (qn, rn) in product(query_names, result_names):
        score = max(score, _align_name_parts(qn, rn))
    return score


def name_literal_match(query: E, result: E) -> float:
    """Two entities have the same name, without normalization applied to the name."""
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, clean_name_light)
    rnames = clean_map(result_names, clean_name_light)
    return 1.0 if has_overlap(qnames, rnames) else 0.0


def name_fingerprint_levenshtein(query: E, result: E) -> float:
    """Two non-person entities have similar fingerprinted names. This includes
    simplifying entity type names (e.g. "Limited" -> "Ltd")."""
    if has_schema(query, result, "Person"):
        return 0.0
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, fingerprint_name)
    qnames.update(clean_map(query_names, clean_name_light))
    rnames = clean_map(result_names, fingerprint_name)
    rnames.update(clean_map(result_names, clean_name_light))
    return compare_sets(qnames, rnames, compare_levenshtein)


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
