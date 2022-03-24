from typing import Iterable, List, Set
from prefixdate import Precision

from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.util import has_disjoint, has_overlap

KEY_DATES = ["birthDate", "incorporationDate", "registrationDate", "startDate"]


def _entity_key_dates(entity: Entity) -> List[str]:
    values = entity.get("birthDate", quiet=True)
    values.extend(entity.get("incorporationDate", quiet=True))
    return values


def _dates_precision(values: Iterable[str], precision: Precision) -> Set[str]:
    dates = set()
    for value in values:
        if len(value) >= precision.value:
            dates.add(value[: precision.value])
    return dates


def key_day_matches(left: Entity, right: Entity) -> float:
    left_days = _dates_precision(_entity_key_dates(left), Precision.DAY)
    right_days = _dates_precision(_entity_key_dates(right), Precision.DAY)
    return has_overlap(left_days, right_days)


def key_year_matches(left: Entity, right: Entity) -> float:
    left_dates = _entity_key_dates(left)
    right_dates = _entity_key_dates(right)
    left_years = _dates_precision(left_dates, Precision.YEAR)
    right_years = _dates_precision(right_dates, Precision.YEAR)
    if len(left_years.intersection(right_dates)) > 0:
        return 1.0
    if len(right_years.intersection(left_dates)) > 0:
        return 1.0
    return 0.0
