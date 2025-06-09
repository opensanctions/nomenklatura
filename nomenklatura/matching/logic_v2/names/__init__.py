from typing import List, Optional, Set
from rigour.names import NameTypeTag
from rigour.names import align_person_name_order
from followthemoney.proxy import E, EntityProxy
from followthemoney import model
from followthemoney.types import registry

from nomenklatura.matching.logic_v2.names.symbols import SymbolName
from nomenklatura.matching.logic_v2.names.analysis import entity_names, schema_type_tag
from nomenklatura.matching.logic_v2.names.heuristics import numbers_mismatch
from nomenklatura.matching.logic_v2.names.pairing import Pairing
from nomenklatura.matching.logic_v2.names.util import strict_levenshtein, normalize_name
from nomenklatura.matching.types import FtResult


def match_name_symbolic(query: SymbolName, result: SymbolName) -> FtResult:
    # print("YYY", query.symbols, result.symbols)
    pairings = [Pairing.create(query, result)]
    result_map = result.symbol_map()
    for part in query.parts:
        next_pairings: List[Pairing] = []
        for qspan in query.spans:
            if part not in qspan.parts:
                continue
            for rspan in result_map.get(qspan.symbol, []):
                for pairing in pairings:
                    if pairing.can_pair(qspan, rspan):
                        next_pairing = pairing.add(qspan, rspan)
                        next_pairings.append(next_pairing)
        if len(next_pairings):
            pairings = next_pairings

    # pairings.append(Pairing.create(query, result))
    max_score = 0.0
    max_pairing = None
    for pairing in pairings:
        query_rem = pairing.query_remainder()
        result_rem = pairing.result_remainder()
        if len(query_rem) == 0:
            max_score = 1.0
            max_pairing = pairing
            continue
        # TODO: ASCII conversion / transliteration?
        # TODO: Align name parts for people
        if query.tag == NameTypeTag.PER:
            alignment = align_person_name_order(query_rem, result_rem)
            if alignment is not None:
                query_rem = alignment.query_sorted + alignment.query_extra
                result_rem = alignment.result_sorted + alignment.result_extra

        query_fuzzy = " ".join([p.maybe_ascii for p in query_rem])
        result_fuzzy = " ".join([p.maybe_ascii for p in result_rem])
        score = strict_levenshtein(query_fuzzy, result_fuzzy)
        if score > max_score:
            max_score = score
            max_pairing = pairing
    detail: Optional[str] = None
    if max_pairing is not None:
        detail = "/".join(str(s) for s in max_pairing.symbols)
    return FtResult(score=max_score, detail=detail)


def _get_object_names(entity: EntityProxy) -> Set[str]:
    """Get the names of an object entity, such as a vessel or asset."""
    names = entity.get_type_values(registry.name, matchable=True)
    if not names:
        return set()
    return set([normalize_name(name) for name in names])


def match_object_names(query: E, result: E) -> FtResult:
    """Match the names of two objects, such as vessels or assets."""
    result_names = _get_object_names(result)
    best_result = FtResult(score=0.0, detail=None)
    for query_name in _get_object_names(query):
        for result_name in result_names:
            score = strict_levenshtein(query_name, result_name, max_rate=5)
            # Things like Vessels, Airplanes, Securities, etc.
            detail = None
            if numbers_mismatch(query_name, result_name):
                score = score * 0.7
                detail = "Number mismatch in name"
            if score > best_result.score:
                best_result = FtResult(score=score, detail=detail)
    return best_result


def name_match(query: E, result: E) -> FtResult:
    """Match two entities by analyzing and comparing their names."""
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    if type_tag == NameTypeTag.UNK:
        # Name matching is not supported for entities that are not listed
        # as a person, organization, or a thing.
        return FtResult(score=0.0, detail=None)
    if type_tag == NameTypeTag.OBJ:
        return match_object_names(query, result)
    query_names = entity_names(type_tag, query, is_query=True)
    result_names = entity_names(type_tag, result)
    best = FtResult(score=0.0, detail=None)
    for query_name in query_names:
        for result_name in result_names:
            ftres = match_name_symbolic(query_name, result_name)
            if ftres.score > best.score:
                best = ftres
    return best
