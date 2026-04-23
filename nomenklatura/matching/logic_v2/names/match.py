from typing import List, Set, Tuple
from rigour.names import NameTypeTag, Name, NamePart
from rigour.names import align_person_name_order, normalize_name
from rigour.names import remove_obj_prefixes
from rigour.names.symbol import pair_symbols
from followthemoney.proxy import E, EntityProxy
from followthemoney import model
from followthemoney.types import registry
from followthemoney.names import schema_type_tag

from nomenklatura.matching.logic_v2.names.analysis import entity_names
from nomenklatura.matching.logic_v2.names.magic import (
    SYM_SCORES,
    SYM_WEIGHTS,
    weight_extra_match,
)
from nomenklatura.matching.logic_v2.names.distance import weighted_edit_similarity
from nomenklatura.matching.logic_v2.names.distance import strict_levenshtein
from nomenklatura.matching.logic_v2.names.util import Match, numbers_mismatch
from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import FNUL


def match_name_symbolic(
    query: Name, result: Name, config: ScoringConfig
) -> Tuple[FtResult, List[Match]]:
    # Stage 1: Generate all valid symbol-based pairings
    # pairings = generate_symbol_pairings(query, result)

    # Stage 2: We compute the score for each pairing, which is a combination of the
    # symbolic match (some types of symbols are considered less strong matches than others) and
    # the fuzzy match of the remaining name parts. Special scoring is also applied for extra
    # name parts that are not matched to the other name during name alignment.
    extra_query_weight = config.get_float("nm_extra_query_name")
    extra_result_weight = config.get_float("nm_extra_result_name")
    family_name_weight = config.get_float("nm_family_name_weight")
    retval = FtResult(score=FNUL, detail=None)
    retmatches: List[Match] = []
    for edges in pair_symbols(query, result):
        matches: List[Match] = []
        for edge in edges:
            match = Match(
                symbol=edge.symbol,
                qps=list(edge.query_parts),
                rps=list(edge.result_parts),
                score=SYM_SCORES.get(edge.symbol.category, 1.0),
                weight=SYM_WEIGHTS.get(edge.symbol.category, 1.0),
            )
            matches.append(match)

        # Remainders — parts not covered by any edge in this pairing
        query_used = {p for edge in edges for p in edge.query_parts}
        result_used = {p for edge in edges for p in edge.result_parts}
        query_rem = [p for p in query.parts if p not in query_used]
        result_rem = [p for p in result.parts if p not in result_used]

        if len(query_rem) > 0 or len(result_rem) > 0:
            if query.tag == NameTypeTag.PER:
                query_rem, result_rem = align_person_name_order(query_rem, result_rem)
            else:
                query_rem = NamePart.tag_sort(query_rem)
                result_rem = NamePart.tag_sort(result_rem)

            matches.extend(weighted_edit_similarity(query_rem, result_rem, config))

        # Apply additional weight and score normalisation to the generated matches based
        # on contextual clues.
        for match in matches:
            # Matches with one side empty, i.e. unmatched parts
            # unmatched result part
            if len(match.qps) == 0:
                bias = weight_extra_match(match.rps, result)
                match.weight = extra_result_weight * bias
            # unmatched query part
            elif len(match.rps) == 0:
                bias = weight_extra_match(match.qps, query)
                match.weight = extra_query_weight * bias
            # We fall through here to apply the family-name boost to unmatched parts too.

            # We have types of symbol matches and where we never score 1.0, but for
            # literal matches, we always want to score 1.0
            if (
                match.score < 1.0
                and len(match.qps) == len(match.rps)
                and match.qps
                and all(
                    q.comparable == r.comparable for q, r in zip(match.qps, match.rps)
                )
            ):
                match.score = 1.0
            # We treat family names matches as more important (but configurable) because
            # they're just globally less murky and changeable than given names.
            if match.is_family_name():
                match.weight *= family_name_weight

        # Sum up and average all the weights to get the final score for this pairing.
        # score = sum(weights) / len(weights) if len(weights) > 0 else 0.0
        total_weight = sum(match.weight for match in matches)
        total_score = sum(match.weighted_score for match in matches)
        score = total_score / total_weight if total_weight > 0 else 0.0
        if score > retval.score:
            # We are not turning the matches into a detail string here because this is the hot
            # path and the string generation takes a non-trivial amount of time. We defer it
            # until the end when we know which matches we will return.
            retmatches = list(matches)
            retval = FtResult(
                score=score,
                query=query.original,
                candidate=result.original,
            )
            if score == 1.0:
                break
    return retval, retmatches


def _get_object_names(entity: EntityProxy) -> Set[str]:
    """Get the names of an object entity, such as a vessel or asset."""
    names = entity.get_type_values(registry.name, matchable=True)
    if not names:
        return set()
    normalized = [normalize_name(name) for name in names]
    return set([n for n in normalized if n is not None])


def match_object_names(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Match the names of two objects, such as vessels or assets."""
    result_names = _get_object_names(result)
    mismatch_penalty = 1 - config.get_float("nm_number_mismatch")
    best_result = FtResult(score=FNUL, detail=None)
    for query_name in _get_object_names(query):
        query_name = remove_obj_prefixes(query_name)
        for result_name in result_names:
            result_name = remove_obj_prefixes(result_name)
            score = strict_levenshtein(query_name, result_name, max_rate=5)
            if score == 1.0:
                detail = f"[{result_name!r} literalMatch]"
            else:
                detail = f"[{query_name!r}≈{result_name!r}, fuzzyMatch: {score:.2f}]"
            if numbers_mismatch(query_name, result_name):
                score = score * mismatch_penalty
                detail = "Number mismatch"
            if score > best_result.score:
                best_result = FtResult(
                    score=score, detail=detail, query=query_name, candidate=result_name
                )
    return best_result


def name_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Match two entities by analyzing and comparing their names."""
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    if type_tag == NameTypeTag.UNK:
        # Name matching is not supported for entities that are not listed
        # as a person, organization, or a thing.
        return FtResult(score=FNUL, detail=None)
    if type_tag == NameTypeTag.OBJ:
        return match_object_names(query, result, config)
    name_prop = config.get_optional_string("nm_name_property")
    query_names = entity_names(query, prop=name_prop, is_query=True)
    result_names = entity_names(result, prop=name_prop)

    # For literal matches, return early instead of performing all the magic. This addresses
    # a user surprise where literal matches can score below 1.0 after name de-duplication has
    # only left a superset name on one side.
    query_comparable = {name.comparable: name for name in query_names}
    result_comparable = {name.comparable: name for name in result_names}
    common = set(query_comparable).intersection(result_comparable)
    if len(common) > 0:
        longest = max(common, key=len)
        match = Match(
            qps=query_comparable[longest].parts,
            rps=result_comparable[longest].parts,
            score=1.0,
        )
        return FtResult(
            score=match.score,
            detail=str(match),
            query=query_comparable[longest].original,
            candidate=result_comparable[longest].original,
        )

    # Remove short names that are contained in longer names.
    # This prevents a scenario where a short version of a name ("John
    # Smith") is matched to a query ("John K Smith"), where a longer version
    # ("John K Smith" != "John R Smith") would have disqualified the match.
    query_names = Name.consolidate_names(query_names)
    result_names = Name.consolidate_names(result_names)

    best = FtResult(score=FNUL, detail=None)
    best_matches: List[Match] = []

    # This combinatorial explosion is the single biggest determinant of the name
    # matching speed: 1 x 1 is very fast, 2 x 5 still good, but 3 x 200 gets out
    # of hand. We need to consider more ways to prune pairs before we do a full
    # symbolic + fuzzy match on them.
    for query_name in query_names:
        for result_name in result_names:
            ftres, ftmatches = match_name_symbolic(query_name, result_name, config)
            if ftres.score >= best.score:
                best = ftres
                best_matches = ftmatches
                if best.score == 1.0:
                    break
    if len(best_matches) > 0 and best.detail is None:
        best.detail = " ".join(str(m) for m in best_matches)
    if best.detail is None:
        best.detail = "No name match found."
    return best
