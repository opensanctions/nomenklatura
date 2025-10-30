from typing import Dict, List

from nomenklatura.matching.types import Feature, HeuristicAlgorithm
from nomenklatura.matching.types import ConfigVar, ConfigVarType
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.identifiers import crypto_wallet_address
from nomenklatura.matching.compare.identifiers import identifier_match
from nomenklatura.matching.compare.dates import dob_day_disjoint, dob_year_disjoint
from nomenklatura.matching.compare.names import weak_alias_match
from nomenklatura.matching.compare.addresses import address_entity_match
from nomenklatura.matching.compare.addresses import address_prop_match
from nomenklatura.matching.logic_v2.names.match import name_match
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
    supporting or contradicting features of the two entities. Its name matcher
    uses a versatile matching algorithm that uses cultural reference data for
    precise and explainable cross-language and cross-script matching.
    """

    NAME = "logic-v2"
    features = [
        Feature(func=name_match, weight=1.0),
        Feature(func=address_entity_match, weight=0.98),
        Feature(func=crypto_wallet_address, weight=0.98),
        Feature(func=isin_security_match, weight=0.98),
        Feature(func=lei_code_match, weight=0.95),
        Feature(func=ogrn_code_match, weight=0.95),
        Feature(func=vessel_imo_mmsi_match, weight=0.95),
        Feature(func=inn_code_match, weight=0.95),
        Feature(func=bic_code_match, weight=0.95),
        Feature(func=uei_code_match, weight=0.95),
        Feature(func=npi_code_match, weight=0.95),
        Feature(func=identifier_match, weight=0.85),
        Feature(func=weak_alias_match, weight=0.8),
        Feature(func=address_prop_match, weight=0.2, qualifier=True),
        Feature(func=country_mismatch, weight=-0.2, qualifier=True),
        Feature(func=dob_year_disjoint, weight=-0.15, qualifier=True),
        Feature(func=dob_day_disjoint, weight=-0.25, qualifier=True),
        Feature(func=gender_mismatch, weight=-0.2, qualifier=True),
    ]
    CONFIG = {
        "nm_name_property": ConfigVar(
            type=ConfigVarType.STRING,
            description="The property to use for name matching. If not set, all name properties are used.",
            default=None,
        ),
        "nm_number_mismatch": ConfigVar(
            type=ConfigVarType.FLOAT,
            description="Penalty for mismatching numbers in object or company names.",
            default=0.3,
        ),
        "nm_extra_query_name": ConfigVar(
            type=ConfigVarType.FLOAT,
            description="Weight for name parts in the query not matched to the result.",
            default=0.8,
        ),
        "nm_extra_result_name": ConfigVar(
            type=ConfigVarType.FLOAT,
            description="Weight for name parts in the result not matched to the query.",
            default=0.2,
        ),
        "nm_family_name_weight": ConfigVar(
            type=ConfigVarType.FLOAT,
            description="Extra weight multiplier for family name in person matches (John Smith vs. John Gruber is clearly distinct).",
            default=1.3,
        ),
        "nm_fuzzy_cutoff_factor": ConfigVar(
            type=ConfigVarType.FLOAT,
            description="Extra factor for when a fuzzy match is triggered in name matching. "
            "Below a certain threshold, a fuzzy match is considered as a non-match (score = 0.0). "
            "Adjusting this multiplier will raise this threshold, making a fuzzy match trigger more leniently.",
            default=1.0,
        ),
    }

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
