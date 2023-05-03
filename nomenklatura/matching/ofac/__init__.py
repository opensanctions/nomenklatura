from typing import Dict
from prefixdate import Precision
from followthemoney.types import registry
from nomenklatura.entity import CE
from nomenklatura.matching.types import MatchingResult, ScoringAlgorithm, FeatureDocs
from nomenklatura.matching.ofac.logic import name_jaro_winkler, soundex_jaro_name_parts
from nomenklatura.matching.ofac.logic import ofac_round_score, is_disjoint
from nomenklatura.matching.util import make_github_url, dates_precision
from nomenklatura.matching.util import props_pair, type_pair


class OFAC249Matcher(ScoringAlgorithm):
    """An algorithm that attempts to emulate the behaviour proposed by the
    US OFAC (FAQ 249) and implemented in their web-based Sanctions Search."""

    # Try to re-produce results from: https://sanctionssearch.ofac.treas.gov/
    # cf. https://ofac.treasury.gov/faqs/topic/1636

    NAME = "ofac-249"

    @classmethod
    def explain(cls) -> FeatureDocs:
        return {
            "name_jaro_winkler": {
                "description": name_jaro_winkler.__doc__,
                "coefficient": 0.5,
                "url": make_github_url(name_jaro_winkler),
            },
            "soundex_jaro_name_parts": {
                "description": soundex_jaro_name_parts.__doc__,
                "coefficient": 0.5,
                "url": make_github_url(soundex_jaro_name_parts),
            },
        }

    @classmethod
    def compare(cls, query: CE, match: CE, rounded: bool = True) -> MatchingResult:
        query_names, match_names = type_pair(query, match, registry.name)
        query_names = [n.lower() for n in query_names]
        match_names = [n.lower() for n in match_names]

        names_jaro = name_jaro_winkler(query_names, match_names)
        soundex_jaro = soundex_jaro_name_parts(query_names, match_names)
        features: Dict[str, float] = {
            "name_jaro_winkler": names_jaro,
            "soundex_jaro_name_parts": soundex_jaro,
        }
        score = max(names_jaro, soundex_jaro)
        if rounded:
            score = ofac_round_score(score)
        return MatchingResult(score=score, features=features)


class OFAC249QualifiedMatcher(ScoringAlgorithm):
    """Same as the US OFAC (FAQ 249) algorithm, but scores will be reduced if a mis-match
    of birth dates and nationalities is found."""

    NAME = "ofac-249-qualified"
    COUNTRIES_DISJOINT = "countries_disjoint"
    DOB_DAY_DISJOINT = "dob_day_disjoint"
    DOB_YEAR_DISJOINT = "dob_year_disjoint"

    @classmethod
    def explain(cls) -> FeatureDocs:
        features = OFAC249Matcher.explain()
        features[cls.COUNTRIES_DISJOINT] = {
            "description": "Both entities are linked to different countries.",
            "coefficient": -0.1,
            "url": make_github_url(OFAC249QualifiedMatcher.compare),
        }
        features[cls.DOB_DAY_DISJOINT] = {
            "description": "Both persons have different birthdays.",
            "coefficient": -0.1,
            "url": make_github_url(OFAC249QualifiedMatcher.compare),
        }
        features[cls.DOB_YEAR_DISJOINT] = {
            "description": "Both persons are born in different years.",
            "coefficient": -0.1,
            "url": make_github_url(OFAC249QualifiedMatcher.compare),
        }
        return features

    @classmethod
    def compare(cls, query: CE, match: CE) -> MatchingResult:
        result = OFAC249Matcher.compare(query, match, rounded=False)
        features = cls.explain()

        result["features"][cls.COUNTRIES_DISJOINT] = 0.0
        query_countries, match_countries = type_pair(query, match, registry.country)
        if is_disjoint(query_countries, match_countries):
            weight = features[cls.COUNTRIES_DISJOINT]["coefficient"]
            result["features"][cls.COUNTRIES_DISJOINT] = weight
            result["score"] += weight

        query_dob, match_dob = props_pair(query, match, ["birthDate"])
        query_days = dates_precision(query_dob, Precision.DAY)
        match_days = dates_precision(match_dob, Precision.DAY)
        result["features"][cls.DOB_DAY_DISJOINT] = 0.0
        if is_disjoint(query_days, match_days):
            weight = features[cls.DOB_DAY_DISJOINT]["coefficient"]
            result["features"][cls.DOB_DAY_DISJOINT] = weight
            result["score"] += weight

        query_years = dates_precision(query_dob, Precision.YEAR)
        match_years = dates_precision(match_dob, Precision.YEAR)
        result["features"][cls.DOB_YEAR_DISJOINT] = 0.0
        if is_disjoint(query_years, match_years):
            weight = features[cls.DOB_YEAR_DISJOINT]["coefficient"]
            result["features"][cls.DOB_YEAR_DISJOINT] = weight
            result["score"] += weight

        return result
