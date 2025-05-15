from typing import List, Optional
from rigour.names import NamePartTag, NamePart
from rigour.text import levenshtein_similarity

from nomenklatura.matching.logic_v2.names.util import GIVEN_NAME_TAGS, FAMILY_NAME_TAGS


class Alignment:
    def __init__(self):
        self.query_sorted: List[NamePart] = []
        self.result_sorted: List[NamePart] = []
        self.query_extra: List[NamePart] = []
        self.result_extra: List[NamePart] = []

    def __len__(self) -> int:
        return max(len(self.query_sorted), len(self.result_sorted))


def check_align_tags(query: NamePart, result: NamePart) -> bool:
    """
    Check if the tags of the query and result name parts can be aligned.

    Args:
        query (NamePart): The name part from the query.
        result (NamePart): The name part from the result.

    Returns:
        bool: True if the tags can be aligned, False otherwise.
    """
    if NamePartTag.ANY in (query.tag, result.tag):
        return True
    if query.tag in GIVEN_NAME_TAGS and result.tag in FAMILY_NAME_TAGS:
        return False
    if query.tag in FAMILY_NAME_TAGS and result.tag in GIVEN_NAME_TAGS:
        return False
    return True


# def align_name_slop(
#     query: List[NamePart], result: List[NamePart], max_slop: int = 2
# ) -> Alignment:
#     """Align name parts of companies and organizations. The idea here is to allow
#     skipping tokens within the entity name if this improves overall match quality,
#     but never to re-order name parts."""
#     query_idx = 0
#     result_idx = 0
#     alignment = Alignment()

#     num_align = max(len(query), len(result))
#     # Goal: produce various alignments between name parts, with the possibility
#     # of skipping `max_slop` name parts in either the query or result in total.
#     # (0,0), (1,1), (2,2), (3,3), extra: (4,_)
#     # (1,0), (2,1), (3,2), (4,3), extra: (0,_)
#     # (0,1), (1,2), (2,3), (3,_), extra: (4,_)

#     # while query_idx < len(query) and result_idx < len(result):
#     #     best_qo = 0
#     #     best_ro = 0
#     #     best_score = 0.0
#     #     # for qo, ro in product(range(max_slop + 1), range(max_slop + 1)):
#     #     #     score = strict_levenshtein(query[query_idx + qo], result[])
#     #     query_idx += best_qo
#     #     result_idx += best_ro

#     return alignment


def align_person_name_parts(query: List[NamePart], result: List[NamePart]) -> Alignment:
    """
    Aligns the name parts of a person name for the query and result based on their
    tags and their string similarity such that the most similar name parts are matched.

    Args:
        query (List[NamePart]): The name parts from the query.
        result (List[NamePart]): The name parts from the result.

    Returns:
        List[Tuple[Optional[NamePart], Optional[NamePart]]]: A list of tuples where each tuple
        contains the aligned name parts from the query and result. If a name part does not have
        a match, it will be None in the corresponding position.
    """
    alignment = Alignment()

    for qpart in sorted(query, key=len, reverse=True):
        best_match: Optional[NamePart] = None
        best_score = 0.0
        for rpart in result:
            if rpart in alignment.result_sorted:
                continue
            if not check_align_tags(qpart, rpart):
                continue
            score = levenshtein_similarity(qpart.maybe_ascii, rpart.maybe_ascii)
            if score > best_score:
                best_score = score
                best_match = rpart

        if best_match is not None:
            alignment.query_sorted.append(qpart)
            alignment.result_sorted.append(best_match)
        else:
            alignment.query_extra.append(qpart)

    if not len(alignment.query_sorted):
        alignment.query_sorted = query
        alignment.result_sorted = result
        return alignment

    for rpart in result:
        if rpart not in alignment.result_sorted:
            alignment.result_extra.append(rpart)

    return alignment
