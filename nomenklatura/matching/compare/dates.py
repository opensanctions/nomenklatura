from typing import Iterable, Set
from prefixdate import Precision
from followthemoney.proxy import E
from rigour.text.distance import dam_levenshtein
from itertools import product

from nomenklatura.matching.compare.util import has_overlap, is_disjoint
from nomenklatura.matching.util import props_pair


MAX_YEARS = 2


def _dates_precision(values: Iterable[str], precision: Precision) -> Set[str]:
    dates = set()
    for value in values:
        if len(value) >= precision.value:
            dates.add(value[: precision.value])
    return dates


def _flip_day_month(value: str) -> str:
    # This is such a common mistake we want to accomodate it.
    year, month, day = value.split("-", 2)
    return f"{year}-{day}-{month}"


def dob_matches(query: E, result: E) -> float:
    """The birth date of the two entities is the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if len(query_dates) == 0 or len(result_dates) == 0:
        return 0.0
    result_days = _dates_precision(result_dates, Precision.DAY)
    query_days = _dates_precision(query_dates, Precision.DAY)
    if has_overlap(query_days, result_days):
        return 1.0
    query_flipped = [_flip_day_month(d) for d in query_days]
    if has_overlap(query_flipped, result_days):
        return 0.5
    return 0.0


def dob_year_matches(query: E, result: E) -> float:
    """The birth date of the two entities is the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    query_years = _dates_precision(query_dates, Precision.YEAR)
    result_years = _dates_precision(result_dates, Precision.YEAR)
    if has_overlap(query_years, result_years):
        return 1.0
    return 0.0


def dob_day_disjoint(query: E, result: E) -> float:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if len(query_dates) == 0 or len(result_dates) == 0:
        return 0.0
    result_days = _dates_precision(result_dates, Precision.DAY)
    query_days = _dates_precision(query_dates, Precision.DAY)
    if len(result_days) == 0 or len(query_days) == 0:
        return 0.0
    if has_overlap(query_days, result_days):
        return 0.0
    query_flipped = [_flip_day_month(d) for d in query_days]
    if has_overlap(query_flipped, result_days):
        return 0.5
    return 1.0


def dob_year_disjoint(query: E, result: E) -> float:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    query_years = _dates_precision(query_dates, Precision.YEAR)
    result_years = _dates_precision(result_dates, Precision.YEAR)
    if is_disjoint(query_years, result_years):
        return 1.0
    return 0.0


def both_have_dob(query: E, result: E) -> float:
    """Both entities have a birth date."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if query_dates and result_dates:
        return 1.0
    return 0.0


def dob_similarity(query: E, result: E) -> float:
    """
    1.0: precise dates match
    0.75: years match
    0.5: dates within 1 edit from each other
    0.25: years within 2 years from each other
    -0.2: imprecise dates are disjoint
    -0.3: precise dates are disjoint
    """
    query_dates, result_dates = props_pair(query, result, ["birthDate"])

    # missing data
    if len(query_dates) == 0 or len(result_dates) == 0:
        return 0.0

    # exact match on precise dates
    result_days = _dates_precision(result_dates, Precision.DAY)
    query_days = _dates_precision(query_dates, Precision.DAY)
    if has_overlap(query_days, result_days):
        return 1.0

    # precise dates available but have no common values
    if is_disjoint(query_days, result_days):
        return -0.3

    # clerical errors on precise dates
    for qd, rd in product(query_days, result_days):
        if dam_levenshtein(qd, rd) <= 1:
            return 0.5

    # years overlap
    query_years = _dates_precision(query_dates, Precision.YEAR)
    result_years = _dates_precision(result_dates, Precision.YEAR)
    if has_overlap(query_years, result_years):
        return 0.75

    # years are close
    for qy, ry in product(query_years, result_years):
        years_difference = abs(int(qy) - int(ry))
        if years_difference <= MAX_YEARS:
            return 0.25

    # dates exist but are disjoint other than above options
    return -0.2
