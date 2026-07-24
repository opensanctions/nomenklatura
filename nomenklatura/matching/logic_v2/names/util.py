import re

from rigour.names import Alignment, Name, NamePartTag


def part_tags_compatible(query: Name, result: Name) -> bool:
    """Check two comparable-equal names for contradicting part roles.

    Guards the literal-match early exit: a query with firstName=Putin,
    lastName=Vladimir produces the same comparable string as a
    "PUTIN, Vladimir"-style alias on the result, but matches the family
    name against the given name. Such pairs must fall through to the
    full alignment machinery, which penalises the role swap, instead of
    short-circuiting to a 1.0 literal match."""
    for qp, rp in zip(query.parts, result.parts):
        if not qp.tag.can_match(rp.tag):
            return False
    return True


def is_family_name(alignment: Alignment) -> bool:
    """True if any covered part on either side carries a FAMILY
    tag — used to apply the family-name weight boost."""
    for np in alignment.qps:
        if np.tag == NamePartTag.FAMILY:
            return True
    for np in alignment.rps:
        if np.tag == NamePartTag.FAMILY:
            return True
    return False


def explain_alignment(alignment: Alignment) -> str:
    """Format an alignment for the API explanation string.

    Surfaces in `MatchingResult.explanations[name_match].detail`,
    one bracketed entry per piece of evidence — symbolic edge,
    fuzzy cluster, or unmatched extra. The leading label
    (`symbolMatch` / `literalMatch` / `fuzzyMatch` /
    `extraQueryPart` / `extraResultPart`) is what makes per-pair
    triage in support tickets possible."""
    qstr = alignment.qstr
    rstr = alignment.rstr
    if alignment.symbol is not None:
        explanation = f"{qstr!r}≈{rstr!r} symbolMatch {alignment.symbol}"
    elif not qstr:
        explanation = f"{rstr!r} extraResultPart"
    elif not rstr:
        explanation = f"{qstr!r} extraQueryPart"
    elif qstr == rstr:
        explanation = f"{rstr!r} literalMatch"
    else:
        explanation = f"{qstr!r}≈{rstr!r} fuzzyMatch"
    return f"[{explanation}: {alignment.score:.2f}, weight {alignment.weight:.2f}]"


NUMERIC = re.compile(r"\d{1,}")


def numbers_mismatch(query: str, result: str) -> bool:
    """Check if the number of numerals in two names is different."""
    query_nums = set(NUMERIC.findall(query))
    result_nums = set(NUMERIC.findall(result))
    return len(query_nums.difference(result_nums)) > 0
