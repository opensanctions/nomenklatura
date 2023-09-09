from typing import List, Optional
from followthemoney.proxy import E
from followthemoney.types import registry
from jellyfish import soundex, jaro_winkler_similarity
from nomenklatura.util import name_words, fingerprint_name
from nomenklatura.matching.util import type_pair, props_pair, compare_sets, has_schema
from nomenklatura.matching.compare.util import is_disjoint, clean_map, has_overlap
from nomenklatura.matching.compare.util import compare_levenshtein


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


def soundex_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the phonetic matching."""
    query_names, result_names = type_pair(query, result, registry.name)
    result_parts = name_words(query_names)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(result_names):
        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0
        similiarities.append(soundex_score)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def jaro_name_parts(query: E, result: E) -> float:
    """Compare two sets of name parts using the Jaro-Winkler string similarity
    algorithm."""
    query_names, result_names = type_pair(query, result, registry.name)
    result_parts = name_words(query_names)
    similiarities: List[float] = []
    for part in name_words(result_names):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            if part_similarity < 0.5:
                part_similarity = 0.0
            best = max(best, part_similarity)

        similiarities.append(best)
    return sum(similiarities) / float(max(1.0, len(similiarities)))


def _sorted_fingerprint(name: str) -> Optional[str]:
    fp = fingerprint_name(name)
    if fp is None:
        return None
    return " ".join(sorted(fp.split(" ")))


def person_name_jaro_winkler(query: E, result: E) -> float:
    """Compare two persons' names using the Jaro-Winkler string similarity algorithm."""
    if not has_schema(query, result, "Person"):
        return 0.0
    query_names, result_names = type_pair(query, result, registry.name)
    qnames = clean_map(query_names, _sorted_fingerprint)
    rnames = clean_map(result_names, _sorted_fingerprint)
    return compare_sets(qnames, rnames, jaro_winkler_similarity)


def last_name_mismatch(left: E, right: E) -> float:
    """The two persons have different last names."""
    lv, rv = props_pair(left, right, ["lastName"])
    lvt = name_words(lv)
    rvt = name_words(rv)
    return 1.0 if is_disjoint(lvt, rvt) else 0.0
