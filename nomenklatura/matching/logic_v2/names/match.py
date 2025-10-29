from typing import Dict, List, Set
from rigour.names import NameTypeTag, Name, NamePart, Span, Symbol
from rigour.names import align_person_name_order, normalize_name
from rigour.names import remove_obj_prefixes
from followthemoney.proxy import E, EntityProxy
from followthemoney import model
from followthemoney.types import registry
from followthemoney.names import schema_type_tag

from nomenklatura.matching.logic_v2.names.analysis import entity_names
from nomenklatura.matching.logic_v2.names.magic import weight_extra_match
from nomenklatura.matching.logic_v2.names.pairing import Pairing
from nomenklatura.matching.logic_v2.names.distance import weighted_edit_similarity
from nomenklatura.matching.logic_v2.names.distance import strict_levenshtein
from nomenklatura.matching.logic_v2.names.util import Match, numbers_mismatch
from nomenklatura.matching.types import FtResult, ScoringConfig


# Step 1: Generate all Matches based on symbols
# Step 2: Generate the most highly-scored sequences of matches
# Step 3: Pick the best sequence


def match_name_symbolic(query: Name, result: Name, config: ScoringConfig) -> FtResult:
    # Stage 1: We create a set of pairings between the symbols that have been annotated as spans
    # on both names. This will try to determine the maximum, non-overlapping set of name
    # parts that can be explained using pre-defined symbols.
    query_symbols: Set[Symbol] = set(span.symbol for span in query.spans)
    pairings = [Pairing.empty()]
    result_map: Dict[Symbol, List[Span]] = {}
    for span in result.spans:
        if span.symbol not in query_symbols:
            continue
        if span.symbol not in result_map:
            result_map[span.symbol] = []
        result_map[span.symbol].append(span)
    seen: Set[int] = set()
    for part in query.parts:
        next_pairings: List[Pairing] = []
        for qspan in query.spans:
            if qspan.symbol not in result_map:
                continue
            if part not in qspan.parts:
                continue
            for rspan in result_map.get(qspan.symbol, []):
                # This assumes that these are the only factors for weighting the
                # resulting match:
                key = hash((qspan.parts, rspan.parts, qspan.symbol.category))
                if key in seen:
                    continue
                for pairing in pairings:
                    if pairing.can_pair(qspan, rspan):
                        seen.add(key)
                        next_pairing = pairing.add(qspan, rspan)
                        next_pairings.append(next_pairing)
        if len(next_pairings):
            pairings = next_pairings

    # Stage 2: We compute the score for each pairing, which is a combination of the
    # symbolic match (some types of symbols are considered less strong matches than others) and
    # the fuzzy match of the remaining name parts. Special scoring is also applied for extra
    # name parts that are not matched to the other name during name alignment.
    extra_query_weight = config.get_float("nm_extra_query_name")
    extra_result_weight = config.get_float("nm_extra_result_name")
    family_name_weight = config.get_float("nm_family_name_weight")
    retval = FtResult(score=0.0, detail=None)
    for pairing in pairings:
        matches: List[Match] = pairing.matches

        # Name parts that have not been tagged with a symbol:
        query_rem = [part for part in query.parts if part not in pairing.query_used]
        result_rem = [part for part in result.parts if part not in pairing.result_used]

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
            if match.score < 1.0 and match.qstr == match.rstr:
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
            detail = " ".join(str(m) for m in matches)
            retval = FtResult(score=score, detail=detail)
    if retval.detail is None:
        retval.detail = f"{query.comparable!r}≉{result.comparable!r}"
    return retval


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
    best_result = FtResult(score=0.0, detail=None)
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
                best_result = FtResult(score=score, detail=detail)
    return best_result


def name_match(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Match two entities by analyzing and comparing their names."""
    schema = model.common_schema(query.schema, result.schema)
    type_tag = schema_type_tag(schema)
    best = FtResult(score=0.0, detail=None)
    if type_tag == NameTypeTag.UNK:
        # Name matching is not supported for entities that are not listed
        # as a person, organization, or a thing.
        best.detail = "Unsuited for name matching: %s" % schema.name
        return best
    if type_tag == NameTypeTag.OBJ:
        return match_object_names(query, result, config)
    name_prop = config.get_optional_string("nm_name_property")
    query_names = entity_names(type_tag, query, prop=name_prop, is_query=True)
    result_names = entity_names(type_tag, result, prop=name_prop)

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
        return FtResult(score=match.score, detail=str(match))

    # Remove short names that are contained in longer names.
    # This prevents a scenario where a short version of a name ("John
    # Smith") is matched to a query ("John K Smith"), where a longer version
    # ("John K Smith" != "John R Smith") would have disqualified the match.
    query_names = Name.consolidate_names(query_names)
    result_names = Name.consolidate_names(result_names)

    for query_name in query_names:
        for result_name in result_names:
            ftres = match_name_symbolic(query_name, result_name, config)
            if ftres.score >= best.score:
                best = ftres
    if best.detail is None:
        best.detail = "No names available for matching"
    return best
