from typing import List, Set
from rigour.names import NameTypeTag
from rigour.names import align_person_name_order, align_name_slop
from rigour.text import levenshtein_similarity
from followthemoney.proxy import E, EntityProxy
from followthemoney import model
from followthemoney.types import registry

from nomenklatura.matching.logic_v2.names.symbols import Symbol, SymbolName
from nomenklatura.matching.logic_v2.names.analysis import entity_names, schema_type_tag
from nomenklatura.matching.logic_v2.names.heuristics import numbers_mismatch
from nomenklatura.matching.logic_v2.names.pairing import Pairing
from nomenklatura.matching.logic_v2.names.util import strict_levenshtein, normalize_name
from nomenklatura.matching.types import FtResult, ScoringConfig

SYM_WEIGHTS = {
    Symbol.Category.ORG_CLASS: 0.75,
    Symbol.Category.INITIAL: 0.75,
    Symbol.Category.NAME: 0.9,
    Symbol.Category.SYMBOL: 0.9,
}


def match_name_symbolic(
    query: SymbolName, result: SymbolName, config: ScoringConfig
) -> FtResult:
    # Stage 1: We create a set of pairings between the symbols that have been annotated
    # on both names. This will try to determine the maximum, non-overlapping set of name
    # parts that can be explained using pre-defined symbols.
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

    # Stage 2: We compute the score for each pairing, which is a combination of the
    # symbolic match (some types of symbols are considered less strong matches than others) and
    # the fuzzy match of the remaining name parts. Special scoring is also applied for extra
    # name parts that are not matched to the other name during name alignment.
    retval = FtResult(score=0.0, detail=None)
    for pairing in pairings:
        weights: List[float] = []

        # Symbols add a fixed weight each to the score, depending on their category. This
        # balances out the potential length of the underlying name parts.
        for symbol, literal in pairing.symbols.items():
            weight = 1.0 if literal else SYM_WEIGHTS.get(symbol.category, 1.0)
            weights.append(weight)

        # Name parts that have not been tagged with a symbol:
        query_rem = pairing.query_remainder()
        result_rem = pairing.result_remainder()
        if len(query_rem) > 0 or len(result_rem) > 0:
            if query.tag == NameTypeTag.PER:
                alignment = align_person_name_order(query_rem, result_rem)
            else:
                alignment = align_name_slop(query_rem, result_rem)

            # Handle name parts that are not matched to the other name.
            for np in alignment.query_extra:
                weights.append(0.5)
            for np in alignment.query_extra:
                weights.append(0.6)

            query_fuzzy = " ".join([p.maybe_ascii for p in alignment.query_sorted])
            result_fuzzy = " ".join([p.maybe_ascii for p in alignment.result_sorted])
            fuzzy_score = levenshtein_similarity(
                query_fuzzy,
                result_fuzzy,
                max_edits=4,
                max_percent=0.3,
            )
            # for np in alignment.query_sorted:
            #     # Make the score drop off more steeply with errors:
            #     weights.append(fuzzy_score**3)
            weights.append(fuzzy_score**2)
        else:
            query_fuzzy = " ".join([p.maybe_ascii for p in query.parts])
            result_fuzzy = " ".join([p.maybe_ascii for p in result.parts])

        # Sum up and average all the weights to get the final score for this pairing.
        # print("XXX", weights)
        score = sum(weights) / len(weights) if len(weights) > 0 else 0.0
        if score > retval.score:
            detail = f"{query_fuzzy} <> {result_fuzzy}"
            if len(pairing.symbols) > 0:
                symbols = ", ".join((str(s) for s in pairing.symbols.keys()))
                detail = f"{detail} (symbolic: {symbols})"
            retval = FtResult(score=score, detail=detail)
    return retval


def _get_object_names(entity: EntityProxy) -> Set[str]:
    """Get the names of an object entity, such as a vessel or asset."""
    names = entity.get_type_values(registry.name, matchable=True)
    if not names:
        return set()
    return set([normalize_name(name) for name in names])


def match_object_names(query: E, result: E, config: ScoringConfig) -> FtResult:
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


def name_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Match two entities by analyzing and comparing their names."""
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    if type_tag == NameTypeTag.UNK:
        # Name matching is not supported for entities that are not listed
        # as a person, organization, or a thing.
        return FtResult(score=0.0, detail=None)
    if type_tag == NameTypeTag.OBJ:
        return match_object_names(query, result, config)
    query_names = entity_names(type_tag, query, is_query=True)
    result_names = entity_names(type_tag, result)
    best = FtResult(score=0.0, detail=None)
    for query_name in query_names:
        for result_name in result_names:
            ftres = match_name_symbolic(query_name, result_name, config)
            if ftres.score > best.score:
                best = ftres
    return best
