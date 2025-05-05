from typing import List
from rigour.names import NameTypeTag, NamePart
from followthemoney.proxy import E
from followthemoney import model

from nomenklatura.matching.logic_v2.names.symbols import SymbolName
from nomenklatura.matching.logic_v2.names.analysis import entity_names, schema_type_tag
from nomenklatura.matching.logic_v2.names.heuristics import numbers_mismatch

# from nomenklatura.matching.logic_v2.names.alignment import align_person_name_parts
from nomenklatura.matching.logic_v2.names.util import strict_levenshtein


class Alignment:
    def __init__(
        self,
        query_parts: List[NamePart],
        result_parts: List[NamePart],
        discount: float = 0.0,
    ) -> None:
        self.query_parts = query_parts
        self.result_parts = result_parts
        self.discount = discount


def match_name_symbolic(query: SymbolName, result: SymbolName) -> float:
    base_score = strict_levenshtein(query.form, result.form)
    # TODO: ASCII conversion / transliteration?
    if query.tag == NameTypeTag.OBJ:
        # Things like Vessels, Airplanes, Securities, etc.
        if numbers_mismatch(query.form, result.form):
            base_score = base_score * 0.7
        return base_score

    shared_symbols = query.symbols.intersection(result.symbols)
    # TODO: Remove shared symbol if name initial and both names are different

    # TODO: Discount: Query and result names have divergent name parts of same type

    query_fuzzy_parts = query.non_symbol_parts(shared_symbols)
    result_fuzzy_parts = result.non_symbol_parts(shared_symbols)
    # unmatched_query_parts = []
    # unmatched_result_parts = []

    # TODO: Align name parts for people
    # if query.tag == NameTypeTag.PER:
    #     aligned = align_person_name_parts(query_fuzzy_parts, result_fuzzy_parts)
    #     for

    if len(query_fuzzy_parts) == 0:
        return 1.0

    query_fuzzy = " ".join([part.form for part in query_fuzzy_parts])
    result_fuzzy = " ".join([part.form for part in result_fuzzy_parts])

    print("XXX", query_fuzzy, result_fuzzy, shared_symbols)
    symbolic_score = strict_levenshtein(query_fuzzy, result_fuzzy)
    return max(base_score, symbolic_score)


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
            score = match_name_symbolic(query_name, result_name)
            if score > best_score:
                best_score = score
    return best_score
