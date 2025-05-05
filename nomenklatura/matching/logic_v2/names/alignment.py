from typing import List, Optional, Tuple
from rigour.names import NamePartTag, NamePart
from rigour.text import levenshtein_similarity

from nomenklatura.matching.logic_v2.names.util import GIVEN_NAME_TAGS, FAMILY_NAME_TAGS


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


def align_person_name_parts(
    query: List[NamePart], result: List[NamePart]
) -> List[Tuple[Optional[NamePart], Optional[NamePart]]]:
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
    aligned_parts: List[Tuple[Optional[NamePart], Optional[NamePart]]] = []
    query_used = [False] * len(query)
    result_used = [False] * len(result)

    for i, q_part in enumerate(query):
        best_match = None
        best_score = 0.0
        for j, r_part in enumerate(result):
            if query_used[i] or result_used[j]:
                continue
            if not check_align_tags(q_part, r_part):
                continue
            score = levenshtein_similarity(q_part.form, r_part.form)
            if score > best_score:
                best_score = score
                best_match = j

        if best_match is not None:
            aligned_parts.append((q_part, result[best_match]))
            query_used[i] = True
            result_used[best_match] = True
        else:
            aligned_parts.append((q_part, None))

    for j, r_part in enumerate(result):
        if not result_used[j]:
            aligned_parts.append((None, r_part))

    return aligned_parts
