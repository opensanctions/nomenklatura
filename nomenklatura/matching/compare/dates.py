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


def dob_matches(left: E, right: E) -> float:
    """The birth date of the two entities is the same."""
    left_dates, right_dates = props_pair(left, right, ["birthDate"])
    if len(left_dates) == 0 or len(right_dates) == 0:
        return 0.0
    right_days = dates_precision(right_dates, Precision.DAY)
    left_days = dates_precision(left_dates, Precision.DAY)
    if has_overlap(left_days, right_days):
        return 1.0
    left_flipped = [flip_day_month(d) for d in left_days]
    if has_overlap(left_flipped, right_days):
        return 0.5
    return 0.0


def dob_year_matches(left: E, right: E) -> float:
    """The birth date of the two entities is the same."""
    left_dates, right_dates = props_pair(left, right, ["birthDate"])
    left_years = dates_precision(left_dates, Precision.YEAR)
    right_years = dates_precision(right_dates, Precision.YEAR)
    if has_overlap(left_years, right_years):
        return 1.0
    return 0.0


def dob_day_disjoint(left: E, right: E) -> float:
    """The birth date of the two entities is not the same."""
    left_dates, right_dates = props_pair(left, right, ["birthDate"])
    if len(left_dates) == 0 or len(right_dates) == 0:
        return 0.0
    right_days = dates_precision(right_dates, Precision.DAY)
    left_days = dates_precision(left_dates, Precision.DAY)
    if has_overlap(left_days, right_days):
        return 0.0
    left_flipped = [flip_day_month(d) for d in left_days]
    if has_overlap(left_flipped, right_days):
        return 0.5
    return 1.0


def dob_year_disjoint(left: E, right: E) -> float:
    """The birth date of the two entities is not the same."""
    left_dates, right_dates = props_pair(left, right, ["birthDate"])
    left_years = dates_precision(left_dates, Precision.YEAR)
    right_years = dates_precision(right_dates, Precision.YEAR)
    if is_disjoint(left_years, right_years):
        return 1.0
    return 0.0
