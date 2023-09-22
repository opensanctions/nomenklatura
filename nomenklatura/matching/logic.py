from typing import Dict, List

from nomenklatura.matching.types import Feature, HeuristicAlgorithm
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
from nomenklatura.matching.compare.names import last_name_mismatch, name_literal_match
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.multi import numbers_mismatch
from nomenklatura.matching.compare.addresses import address_entity_match


class LogicV1(HeuristicAlgorithm):
    """A rule-based matching system that generates a set of basic scores via
    name and identifier-based matching, and then qualifies that score using
    supporting or contradicting features of the two entities."""

    NAME = "logic-v1"
    features = [
        Feature(func=name_literal_match, weight=1.0),
        Feature(func=person_name_jaro_winkler, weight=0.8),
        Feature(func=person_name_phonetic_match, weight=0.9),
        Feature(func=name_fingerprint_levenshtein, weight=0.9),
        Feature(func=address_entity_match, weight=0.98),
        Feature(func=crypto_wallet_address, weight=0.98),
        Feature(func=isin_security_match, weight=0.98),
        Feature(func=lei_code_match, weight=0.95),
        Feature(func=ogrn_code_match, weight=0.95),
        Feature(func=vessel_imo_mmsi_match, weight=0.95),
        Feature(func=inn_code_match, weight=0.9),
        Feature(func=identifier_match, weight=0.85),
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
