from typing import Dict, List

from nomenklatura.matching.types import Feature, HeuristicAlgorithm, FtResult
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.identifiers import orgid_disjoint
from nomenklatura.matching.compare.identifiers import crypto_wallet_address
from nomenklatura.matching.compare.identifiers import identifier_match
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.compare.names import weak_alias_match
from nomenklatura.matching.compare.addresses import address_entity_match
from nomenklatura.matching.compare.addresses import address_prop_match
from nomenklatura.matching.logic_v2.names import name_match
from nomenklatura.matching.logic_v2.identifiers import bic_code_match
from nomenklatura.matching.logic_v2.identifiers import inn_code_match, ogrn_code_match
from nomenklatura.matching.logic_v2.identifiers import isin_security_match
from nomenklatura.matching.logic_v2.identifiers import lei_code_match
from nomenklatura.matching.logic_v2.identifiers import vessel_imo_mmsi_match
from nomenklatura.matching.logic_v2.identifiers import uei_code_match
from nomenklatura.matching.logic_v2.identifiers import npi_code_match
from nomenklatura.matching.util import FNUL


class LogicV2(HeuristicAlgorithm):
    """A rule-based matching system that generates a set of basic scores via
    name and identifier-based matching, and then qualifies that score using
    supporting or contradicting features of the two entities. Version 2 uses
    a different set of features and consolidates name matching into a single
    feature, which uses a versatile and complex name matching algorithm."""

    NAME = "UNSTABLE-logic-v2"
    features = [
        Feature(func=name_match, weight=1.0),
        Feature(func=FtResult.wrap(address_entity_match), weight=0.98),
        Feature(func=FtResult.wrap(crypto_wallet_address), weight=0.98),
        Feature(func=FtResult.wrap(isin_security_match), weight=0.98),
        Feature(func=FtResult.wrap(lei_code_match), weight=0.95),
        Feature(func=FtResult.wrap(ogrn_code_match), weight=0.95),
        Feature(func=FtResult.wrap(vessel_imo_mmsi_match), weight=0.95),
        Feature(func=FtResult.wrap(inn_code_match), weight=0.95),
        Feature(func=FtResult.wrap(bic_code_match), weight=0.95),
        Feature(func=FtResult.wrap(uei_code_match), weight=0.95),
        Feature(func=FtResult.wrap(npi_code_match), weight=0.95),
        Feature(func=FtResult.wrap(identifier_match), weight=0.85),
        Feature(func=FtResult.wrap(weak_alias_match), weight=0.8),
        Feature(func=FtResult.wrap(address_prop_match), weight=0.2, qualifier=True),
        Feature(func=FtResult.wrap(country_mismatch), weight=-0.2, qualifier=True),
        Feature(func=FtResult.wrap(dob_year_disjoint), weight=-0.15, qualifier=True),
        Feature(func=FtResult.wrap(dob_day_disjoint), weight=-0.25, qualifier=True),
        Feature(func=FtResult.wrap(gender_mismatch), weight=-0.2, qualifier=True),
        Feature(func=FtResult.wrap(orgid_disjoint), weight=-0.2, qualifier=True),
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
