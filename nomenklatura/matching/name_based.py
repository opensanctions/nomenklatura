from typing import Dict, List

from nomenklatura.matching.types import Feature, HeuristicAlgorithm
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.identifiers import orgid_disjoint
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.compare.names import soundex_name_parts, jaro_name_parts


class NameMatcher(HeuristicAlgorithm):
    """An algorithm that matches on entity name, using phonetic comparisons and edit
    distance to generate potential matches. This implementation is vaguely based on
    the behaviour proposed by the US OFAC documentation (FAQ #249)."""

    # Try to re-produce results from: https://sanctionssearch.ofac.treas.gov/
    # cf. https://ofac.treasury.gov/faqs/topic/1636

    NAME = "name-based"
    features = [
        Feature(func=jaro_name_parts, weight=0.5),
        Feature(func=soundex_name_parts, weight=0.5),
    ]

    @classmethod
    def compute_score(cls, weights: Dict[str, float]) -> float:
        return sum(weights.values()) / float(len(weights))


class NameQualifiedMatcher(HeuristicAlgorithm):
    """Same as the name-based algorithm, but scores will be reduced if a mis-match
    of birth dates and nationalities is found for persons, or different
    tax/registration identifiers are included for organizations and companies."""

    NAME = "name-qualified"
    features = [
        Feature(func=jaro_name_parts, weight=0.5),
        Feature(func=soundex_name_parts, weight=0.5),
        Feature(func=country_mismatch, weight=-0.1, qualifier=True),
        Feature(func=dob_year_disjoint, weight=-0.1, qualifier=True),
        Feature(func=dob_day_disjoint, weight=-0.15, qualifier=True),
        Feature(func=gender_mismatch, weight=-0.1, qualifier=True),
        Feature(func=orgid_disjoint, weight=-0.1, qualifier=True),
    ]

    @classmethod
    def compute_score(cls, weights: Dict[str, float]) -> float:
        scores: List[float] = []
        for feature in cls.features:
            if not feature.qualifier:
                scores.append(weights.get(feature.name, 0.0))
        score = sum(scores) / float(len(scores))
        for feature in cls.features:
            if feature.qualifier:
                weight = weights.get(feature.name, 0.0) * feature.weight
                score += weight
        return score
