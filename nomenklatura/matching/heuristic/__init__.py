from typing import Dict, List
from nomenklatura.matching.heuristic.feature import Feature, HeuristicAlgorithm
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.identifiers import orgid_disjoint
from nomenklatura.matching.compare.identifiers import crypto_wallet_address
from nomenklatura.matching.compare.identifiers import inn_code_match, ogrn_code_match
from nomenklatura.matching.compare.identifiers import lei_code_match, identifier_match
from nomenklatura.matching.compare.identifiers import isin_security_match
from nomenklatura.matching.compare.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.compare.names import person_name_phonetic_match
from nomenklatura.matching.compare.names import soundex_name_parts, jaro_name_parts
from nomenklatura.matching.compare.names import last_name_mismatch, name_literal_match
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.multi import numbers_mismatch
from nomenklatura.matching.compare.addresses import address_entity_match


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


class LogicV1(HeuristicAlgorithm):
    """A rule-based matching system that generates a set of basic scores via
    name and identifier-based matching, and then qualifies that score using
    supporting or contradicting features of the two entities."""

    NAME = "logic-v1"
    features = [
        Feature(func=person_name_jaro_winkler, weight=0.8),
        Feature(func=person_name_phonetic_match, weight=0.8),
        Feature(func=name_literal_match, weight=1.0),
        Feature(func=name_fingerprint_levenshtein, weight=0.9),
        Feature(func=address_entity_match, weight=0.98),
        Feature(func=crypto_wallet_address, weight=0.98),
        Feature(func=isin_security_match, weight=0.98),
        Feature(func=lei_code_match, weight=0.95),
        Feature(func=ogrn_code_match, weight=0.95),
        Feature(func=vessel_imo_mmsi_match, weight=0.95),
        Feature(func=inn_code_match, weight=0.9),
        Feature(func=identifier_match, weight=0.8),
        Feature(func=country_mismatch, weight=-0.2, qualifier=True),
        Feature(func=last_name_mismatch, weight=-0.2, qualifier=True),
        Feature(func=dob_year_disjoint, weight=-0.15, qualifier=True),
        Feature(func=dob_day_disjoint, weight=-0.2, qualifier=True),
        Feature(func=gender_mismatch, weight=-0.2, qualifier=True),
        Feature(func=orgid_disjoint, weight=-0.2, qualifier=True),
        Feature(func=numbers_mismatch, weight=-0.1, qualifier=True),
    ]

    @classmethod
    def compute_score(cls, weights: Dict[str, float]) -> float:
        scores: List[float] = []
        for feature in cls.features:
            if not feature.qualifier:
                weight = weights.get(feature.name, 0.0) * feature.weight
                scores.append(weight)
        score = max(scores)
        for feature in cls.features:
            if feature.qualifier:
                weight = weights.get(feature.name, 0.0) * feature.weight
                score += weight
        return score
