from typing import Dict, List

from nomenklatura.matching.types import Feature, HeuristicAlgorithm, FtResult
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.identifiers import crypto_wallet_address
from nomenklatura.matching.compare.identifiers import identifier_match
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.compare.names import person_name_jaro_winkler
from nomenklatura.matching.compare.names import last_name_mismatch, name_literal_match
from nomenklatura.matching.compare.names import name_fingerprint_levenshtein
from nomenklatura.matching.compare.names import weak_alias_match
from nomenklatura.matching.compare.addresses import address_entity_match
from nomenklatura.matching.logic_v1.phonetic import person_name_phonetic_match
from nomenklatura.matching.logic_v1.phonetic import name_soundex_match
from nomenklatura.matching.logic_v1.phonetic import name_metaphone_match
from nomenklatura.matching.logic_v1.identifiers import bic_code_match
from nomenklatura.matching.logic_v1.identifiers import inn_code_match, ogrn_code_match
from nomenklatura.matching.logic_v1.identifiers import isin_security_match
from nomenklatura.matching.logic_v1.identifiers import lei_code_match
from nomenklatura.matching.logic_v1.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.logic_v1.identifiers import orgid_disjoint
from nomenklatura.matching.logic_v1.multi import numbers_mismatch
from nomenklatura.matching.util import FNUL


class LogicV1(HeuristicAlgorithm):
    """A rule-based matching system that generates a set of basic scores via
    name and identifier-based matching, and then qualifies that score using
    supporting or contradicting features of the two entities.
    
    This algorithm has been superseeded by logic-v2 and is no longer
    recommended for new integrations."""

    NAME = "logic-v1"
    features = [
        Feature(func=name_literal_match, weight=1.0),
        Feature(func=FtResult.wrap(person_name_jaro_winkler), weight=0.8),
        Feature(func=FtResult.wrap(person_name_phonetic_match), weight=0.9),
        Feature(func=FtResult.wrap(name_fingerprint_levenshtein), weight=0.9),
        # These are there so they can be enabled using custom weights:
        Feature(func=FtResult.wrap(name_metaphone_match), weight=FNUL),
        Feature(func=FtResult.wrap(name_soundex_match), weight=FNUL),
        Feature(func=address_entity_match, weight=0.98),
        Feature(func=crypto_wallet_address, weight=0.98),
        Feature(func=isin_security_match, weight=0.98),
        Feature(func=lei_code_match, weight=0.95),
        Feature(func=ogrn_code_match, weight=0.95),
        Feature(func=vessel_imo_mmsi_match, weight=0.95),
        Feature(func=inn_code_match, weight=0.95),
        Feature(func=bic_code_match, weight=0.95),
        Feature(func=identifier_match, weight=0.85),
        Feature(func=weak_alias_match, weight=0.8),
        Feature(func=country_mismatch, weight=-0.2, qualifier=True),
        Feature(func=FtResult.wrap(last_name_mismatch), weight=-0.2, qualifier=True),
        Feature(func=dob_year_disjoint, weight=-0.15, qualifier=True),
        Feature(func=dob_day_disjoint, weight=-0.2, qualifier=True),
        Feature(func=gender_mismatch, weight=-0.2, qualifier=True),
        Feature(func=orgid_disjoint, weight=-0.2, qualifier=True),
        Feature(func=numbers_mismatch, weight=-0.1, qualifier=True),
    ]

    @classmethod
    def compute_score(
        cls, scores: Dict[str, float], weights: Dict[str, float]
    ) -> float:
        mains: List[float] = []
        for feat in cls.features:
            if feat.qualifier:
                continue
            weight = scores.get(feat.name, FNUL) * weights.get(feat.name, FNUL)
            mains.append(weight)
        score = max(mains)
        for feat in cls.features:
            if not feat.qualifier:
                continue
            weight = scores.get(feat.name, FNUL) * weights.get(feat.name, FNUL)
            score += weight
        return score
