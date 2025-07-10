import re

NUMERIC = re.compile(r"\d{1,}")


def numbers_mismatch(query: str, result: str) -> bool:
    """Check if the number of numerals in two names is different."""
    query_nums = set(NUMERIC.findall(query))
    result_nums = set(NUMERIC.findall(result))
    return len(query_nums.difference(result_nums)) > 0
