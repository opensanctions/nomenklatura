from typing import Iterable, Set
from prefixdate import Precision
from followthemoney.proxy import E

from nomenklatura.matching.compare.util import has_overlap, is_disjoint
from nomenklatura.matching.util import props_pair


def dates_precision(values: Iterable[str], precision: Precision) -> Set[str]:
    dates = set()
    for value in values:
        if len(value) >= precision.value:
            dates.add(value[: precision.value])
    return dates


def flip_day_month(value: str) -> str:
    # This is such a common mistake we want to accomodate it.
    year, month, day = value.split("-", 2)
    return f"{year}-{day}-{month}"


def dob_matches(query: E, result: E) -> float:
    """The birth date of the two entities is the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if len(query_dates) == 0 or len(result_dates) == 0:
        return 0.0
    result_days = dates_precision(result_dates, Precision.DAY)
    query_days = dates_precision(query_dates, Precision.DAY)
    if has_overlap(query_days, result_days):
        return 1.0
    query_flipped = [flip_day_month(d) for d in query_days]
    if has_overlap(query_flipped, result_days):
        return 0.5
    return 0.0


def dob_year_matches(query: E, result: E) -> float:
    """The birth date of the two entities is the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    query_years = dates_precision(query_dates, Precision.YEAR)
    result_years = dates_precision(result_dates, Precision.YEAR)
    if has_overlap(query_years, result_years):
        return 1.0
    return 0.0


def dob_day_disjoint(query: E, result: E) -> float:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if len(query_dates) == 0 or len(result_dates) == 0:
        return 0.0
    result_days = dates_precision(result_dates, Precision.DAY)
    query_days = dates_precision(query_dates, Precision.DAY)
    if has_overlap(query_days, result_days):
        return 0.0
    query_flipped = [flip_day_month(d) for d in query_days]
    if has_overlap(query_flipped, result_days):
        return 0.5
    return 1.0


def dob_year_disjoint(query: E, result: E) -> float:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    query_years = dates_precision(query_dates, Precision.YEAR)
    result_years = dates_precision(result_dates, Precision.YEAR)
    if is_disjoint(query_years, result_years):
        return 1.0
    return 0.0
