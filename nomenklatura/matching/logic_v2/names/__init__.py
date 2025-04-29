from rigour.names import NameTypeTag
from rigour.text import levenshtein_similarity
from followthemoney.proxy import E
from followthemoney import model

from nomenklatura.matching.logic_v2.names.symbols import SymbolName
from nomenklatura.matching.logic_v2.names.analysis import entity_names, schema_type_tag
from nomenklatura.matching.logic_v2.names.heuristics import numers_mismatch


def match_names(query: SymbolName, result: SymbolName) -> float:
    if query.tag == NameTypeTag.OBJ:
        # Things like Vessels, Airplanes, Securities, etc.
        score = levenshtein_similarity(query.form, result.form)
        if numers_mismatch(query.form, result.form):
            return score * 0.7
        return score

    return levenshtein_similarity(query.form, result.form)


def name_match(query: E, result: E) -> float:
    """Match two entities by analyzing and comparing their names."""
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    if type_tag == NameTypeTag.UNK:
        # Name matching is not supported for entities that are not listed
        # as a person, organization, or a thing.
        return 0.0
    query_names = entity_names(type_tag, query, is_query=True)
    result_names = entity_names(type_tag, result)
    best_score = 0.0
    for query_name in query_names:
        for result_name in result_names:
            score = match_names(query_name, result_name)
            if score > best_score:
                best_score = score
    return best_score
