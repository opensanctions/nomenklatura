from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.compare.util import extract_numbers
from nomenklatura.matching.util import type_pair, has_schema


def numbers_mismatch(query: E, result: E) -> float:
    """Find numbers in names and addresses and penalise different numbers."""
    if has_schema(query, result, "Address"):
        qv, rv = type_pair(query, result, registry.address)
    else:
        qv, rv = type_pair(query, result, registry.name)
    qvn = extract_numbers(qv)
    rvn = extract_numbers(rv)
    base = min(len(qvn), len(rvn))
    mismatch = len(qvn.difference(rvn))
    # print("numbers_mismatch", mismatch, base, qvn, rvn)
    return float(mismatch) / float(max(1, base))
