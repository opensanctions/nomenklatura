import math
import itertools
from typing import List
from rapidfuzz.distance import Levenshtein
from rigour.env import MAX_NAME_LENGTH
from rigour.names import NamePart, NamePartTag
from rigour.text.distance import dam_levenshtein, levenshtein

SIMILAR_PAIRS = [
    ("0", "o"),
    ("1", "i"),
    ("g", "9"),
    ("e", "i"),
    ("1", "l"),
    ("o", "u"),
    ("i", "j"),
    ("c", "k"),
]
SIMILAR_PAIRS = SIMILAR_PAIRS + [(b, a) for a, b in SIMILAR_PAIRS]


def levenshtein_similarity(query: str, result: str) -> float:
    if len(query) == 0 or len(result) == 0:
        return 0.0
    if query == result:
        return 1.0
    max_len = max(len(query), len(result))
    max_edits = math.floor(math.log(max(max_len - 2, 1)))
    if max_edits < 1:
        return 0.0
    distance = dam_levenshtein(query, result, max_edits=max_edits)
    if distance > max_edits:
        return 0.0
    score = 1 - (distance / max_len)
    score = score**2
    if score < 0.5:
        score = 0.0
    return score


def strict_levenshtein(left: str, right: str, max_rate: int = 4) -> float:
    """Calculate the string distance between two strings."""
    if left == right:
        return 1.0
    max_len = max(len(left), len(right))
    max_edits = max_len // max_rate
    if max_edits < 1:  # We already checked for equality
        return 0.0
    distance = levenshtein(left, right, max_edits=max_len)
    if distance > max_edits:
        return 0.0
    return (1 - (distance / max_len)) ** max_edits


def weighted_edit_similarity(
    src_parts: List[NamePart],
    dest_parts: List[NamePart],
) -> float:
    """Calculate a weighted similarity score between two sets of name parts."""
    if len(src_parts) == 0 or len(dest_parts) == 0:
        return 0.0
    src_tokens = [p.comparable for p in src_parts]
    dest_tokens = [p.comparable for p in dest_parts]
    src_text = " ".join(src_tokens)[:MAX_NAME_LENGTH]
    dest_text = " ".join(dest_tokens)[:MAX_NAME_LENGTH]
    if src_text == dest_text:
        return 1.0
    if len(src_text) < 4 or len(dest_text) < 4:
        # Too short to fuzzy match
        return 0.0
    total_distance = 0.0
    # TODO build a set of matches (nee Pairing), aligning token name parts of src and dest
    # to each other. Compute a score (based on edits) and weight (dependent on type) for each.
    # Use editops to iterate over the differences between the two texts character by character.
    #
    # When does a bundle gets made as a match, and when not?
    src_offset = 0
    dest_offset = 0
    for op in Levenshtein.opcodes(src_text, dest_text):
        # src_offset += op.src_end - op.src_start
        # dest_offset += op.dest_end - op.dest_start

        if op.tag == "equal":
            continue

    src_seen: List[NamePart] = []
    src_token_start, src_offset = 0, 0
    dest_seen: List[NamePart] = []
    dest_token_start, dest_offset = 0, 0
    for op in Levenshtein.opcodes(src_text, dest_text):
        src_token = (
            src_tokens[len(src_seen)] if len(src_seen) < len(src_tokens) else None
        )
        dest_token = (
            dest_tokens[len(dest_seen)] if len(dest_seen) < len(dest_tokens) else None
        )
        if op.tag == "equal":
            continue
        src_part = src_text[op.src_start : op.src_end]
        dest_part = dest_text[op.dest_start : op.dest_end]
        # Cases:
        # - Full token insertion or deletion
        # - Cheap replacement of a single character
        # - Numeric addition or deletion
        # - Space insert or deletion
        distance = float(len(src_part) + len(dest_part))
        for s, d in itertools.zip_longest(src_part, dest_part):
            if d is None:
                if s == " ":
                    # Space deletion
                    distance -= 0.8
                elif s.isdigit():
                    # Numeric deletion
                    distance += 1.0
            elif s is None:
                if d == " ":
                    # Space insertion
                    distance -= 0.8
                elif d.isdigit():
                    # Numeric insertion
                    distance += 1.0
            elif (s, d) in SIMILAR_PAIRS:
                # Similar character replacement, e.g. 0 and o
                distance -= 1.0

        if op.tag == "delete" and src_part in src_tokens:
            # Remove a full token (in query but not in result)
            part = src_parts[src_tokens.index(src_part)]
            # TODO: check if legal or ordinal, then it's less severe
            if part.tag != NamePartTag.NUMERIC:
                distance = 1.0
        elif op.tag == "insert" and dest_part in dest_tokens:
            # Add a full token (in result but not in query)
            distance = 1.0

        total_distance += distance

    max_len = max(len(src_text), len(dest_text))
    # max_edits = math.floor(math.log(max(max_len - 2, 1)))
    # if total_distance > max_edits:
    #     return 0.0
    score = (1.0 - (total_distance / max_len)) ** 2
    if score < 0.5:
        score = 0.0
    return score
