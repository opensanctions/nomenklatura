from typing import Iterable, Set
from prefixdate import Precision
from followthemoney.proxy import E

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.compare.util import has_overlap
from nomenklatura.matching.util import props_pair


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


def dob_day_disjoint(query: E, result: E, config: ScoringConfig) -> FtResult:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    if len(query_dates) == 0 or len(result_dates) == 0:
        return FtResult(score=0.0, detail="No birth dates provided")
    result_days = _dates_precision(result_dates, Precision.DAY)
    query_days = _dates_precision(query_dates, Precision.DAY)
    if len(result_days) == 0 or len(query_days) == 0:
        return FtResult(score=0.0, detail="No birth days provided")
    if has_overlap(query_days, result_days):
        match = ", ".join(query_days.intersection(result_days))
        detail = f"Birth day match: {match}"
        return FtResult(score=0.0, detail=detail)
    query_flipped = [_flip_day_month(d) for d in query_days]
    if has_overlap(query_flipped, result_days):
        match = ", ".join(result_days.intersection(query_flipped))
        detail = f"Birth day mis-match (flipped): {match}"
        return FtResult(score=0.5, detail=detail)
    detail = f"Birth day mis-match: {', '.join(query_days)} vs {', '.join(result_days)}"
    return FtResult(score=1.0, detail=detail)


def dob_year_disjoint(query: E, result: E, config: ScoringConfig) -> FtResult:
    """The birth date of the two entities is not the same."""
    query_dates, result_dates = props_pair(query, result, ["birthDate"])
    query_years = _dates_precision(query_dates, Precision.YEAR)
    result_years = _dates_precision(result_dates, Precision.YEAR)
    if len(query_years) == 0 or len(result_years) == 0:
        return FtResult(score=0.0, detail="No birth years provided")
    common = query_years.intersection(result_years)
    if len(common) > 0:
        detail = f"Birth year match: {', '.join(common)}"
        return FtResult(score=0.0, detail=detail)
    detail = f"Birth years: {', '.join(query_years)} vs {', '.join(result_years)}"
    return FtResult(score=1.0, detail=detail)
