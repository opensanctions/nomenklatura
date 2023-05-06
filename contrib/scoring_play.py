from typing import List, Set, Union
from jellyfish import soundex, jaro_winkler_similarity
from followthemoney import model
from nomenklatura.entity import CompositeEntity
from nomenklatura.matching.util import compare_sets
from nomenklatura.util import name_words


def soundex_jaro_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two strings using the Soundex algorithm and Jaro-Winkler."""
    result_parts = name_words(result)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(query):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            best = max(best, part_similarity)

        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0

        # OFAC is very unspecific on this part, so this is a best guess:
        part_score = (best + soundex_score) / 2

        similiarities.append(part_score)
    return sum(similiarities) / float(len(similiarities))


def soundex_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two strings using the Soundex algorithm and Jaro-Winkler."""
    result_parts = name_words(result)
    result_soundex = [soundex(p) for p in result_parts]
    similiarities: List[float] = []
    for part in name_words(query):
        part_soundex = soundex(part)
        soundex_score = 1.0 if part_soundex in result_soundex else 0.0
        similiarities.append(soundex_score)
    return sum(similiarities) / float(len(similiarities))


def jaro_name_parts(query: List[str], result: List[str]) -> float:
    """Compare two strings using the Soundex algorithm and Jaro-Winkler."""
    result_parts = name_words(result)
    similiarities: List[float] = []
    for part in name_words(query):
        best = 0.0

        for other in result_parts:
            part_similarity = jaro_winkler_similarity(part, other)
            if part_similarity < 0.5:
                part_similarity = 0.0
            best = max(best, part_similarity)

        similiarities.append(best)
    return sum(similiarities) / float(len(similiarities))


def name_jaro_winkler(query: List[str], result: List[str]) -> float:
    """Compute Jaro-Winkler string similarity on whole names."""
    return compare_sets(query, result, jaro_winkler_similarity)


def ofac_round_score(score: float, precision: float = 0.05) -> float:
    """OFAC seems to return scores in steps of 5, ie. 100, 95, 90, 85, etc."""
    correction = 0.5 if score >= 0 else -0.5
    return round(int(score / precision + correction) * precision, 2)


def is_disjoint(
    left: Union[Set[str], List[str]],
    right: Union[Set[str], List[str]],
) -> float:
    """Returns 1.0 if both sequences are non-empty but have no common values."""
    if len(left) and len(right):
        if set(left).isdisjoint(right):
            return True
    return False


def compare_name_pair(query: str, result: str):
    # query_data = {"schema": "Person", "properties": {"name": [query]}}
    # query_entity = CompositeEntity.from_dict(model, query_data)
    # result_data = {"schema": "Person", "properties": {"name": [result]}}
    # result_entity = CompositeEntity.from_dict(model, result_data)
    print("Compare: %r <> %r" % (query, result))
    print("  -> name_jaro_winkler: %.3f" % name_jaro_winkler([query], [result]))
    soundex_ = soundex_jaro_name_parts([query], [result])
    print("  -> soundex_jaro_name_parts: %.3f" % soundex_)
    soundex_2 = soundex_name_parts([query], [result])
    print("  -> soundex_name_parts: %.3f" % soundex_2)
    jaro_parts = jaro_name_parts([query], [result])
    print("  -> jaro_name_parts: %.3f" % jaro_parts)


if __name__ == "__main__":
    compare_name_pair("Vladimir Putin", "Vladimir Putin")
    compare_name_pair("Vladimir Putin", "Vladimir Pudin")
    compare_name_pair("Vladimir Putin", "Vladimir Vladimirovitch Putin")
    compare_name_pair("Vladimir Putin", "Will Wheaton")
    compare_name_pair("Angel Rodriguez", "Miguel Angel RODRIGUEZ OREJUELA")
    compare_name_pair("Nathanael Meyers", "Nathaniel McGill")
    compare_name_pair("Siemens AG", "Siemens Aktiengesellschaft")
    compare_name_pair("Gazprom Neft", "ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО 'ГАЗПРОМ НЕФТЬ'")
