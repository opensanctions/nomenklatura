from typing import Dict

from nomenklatura.matching.types import Feature, HeuristicAlgorithm
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.name_based.misc import orgid_disjoint
from nomenklatura.matching.name_based.misc import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.name_based.names import jaro_name_parts
from nomenklatura.matching.name_based.names import soundex_name_parts
from nomenklatura.matching.name_based.ofac import ofac_name_score


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
    def compute_score(
        cls, scores: Dict[str, float], weights: Dict[str, float]
    ) -> float:
        score = 0.0
        for feat in cls.features:
            score += scores.get(feat.name, 0.0) * weights.get(feat.name, 0.0)
        return score


class OFACMatcher(HeuristicAlgorithm):
    """An algorithm that emulates the public OFAC Sanctions List Search tool at
    sanctionssearch.ofac.treas.gov, with mismatch qualifiers layered on top.
    Reverse-engineered from FAQ 249 and parity fixtures captured against the
    live tool. Name scoring tracks OFAC's reported score within +/-5 points on
    the parity fixture. Qualifier features (country, DOB, gender, orgid
    mismatches) reduce the name score - this departs from FAQ 251 (which says
    only the name field influences the Score) but mirrors how OFAC users
    actually triage matches via FAQ 5."""

    NAME = "ofac"
    features = [
        Feature(func=ofac_name_score, weight=1.0),
        Feature(func=country_mismatch, weight=-0.1, qualifier=True),
        Feature(func=dob_year_disjoint, weight=-0.1, qualifier=True),
        Feature(func=dob_day_disjoint, weight=-0.15, qualifier=True),
        Feature(func=gender_mismatch, weight=-0.1, qualifier=True),
        Feature(func=orgid_disjoint, weight=-0.1, qualifier=True),
    ]

    @classmethod
    def compute_score(
        cls, scores: Dict[str, float], weights: Dict[str, float]
    ) -> float:
        score = 0.0
        for feat in cls.features:
            score += scores.get(feat.name, 0.0) * weights.get(feat.name, 0.0)
        return score


class NameQualifiedMatcher(HeuristicAlgorithm):
    # update these two
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
    def compute_score(
        cls, scores: Dict[str, float], weights: Dict[str, float]
    ) -> float:
        score = 0.0
        for feat in cls.features:
            score += scores.get(feat.name, 0.0) * weights.get(feat.name, 0.0)
        return score
