"""Naïve baseline: Levenshtein similarity over casefolded strings.

No analysis, no symbol pairing, no part-aware alignment. Surfaces
the unconditional baseline number to beat.
"""

from __future__ import annotations

from rigour.text.distance import levenshtein_similarity


def levenshtein_baseline(name1: str, name2: str, schema: str) -> float:
    """Score the casefolded raw strings via rigour's Levenshtein similarity.

    `schema` is accepted for the Comparator signature contract but
    ignored here.
    """
    return levenshtein_similarity(name1.casefold().strip(), name2.casefold().strip())
