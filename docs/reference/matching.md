# Matching

A scoring algorithm compares two entities and returns a score between 0.0 and 1.0, together with per-feature explanations of how that score came about.

Matching is used in two distinct situations, and different algorithms fit each. In **screening**, a query entity (e.g. a customer record) is compared against a list of known entities, and false negatives are costly. In **deduplication**, entities from overlapping datasets are compared to find records describing the same real-world entity, and the score is a ranking aid for a human reviewer or an auto-merge threshold.

## Available algorithms

Each algorithm is identified by a stable name, which is used to select it in the [yente API](https://yente.followthemoney.tech/) and on the `nk` command line (`nk xref --algorithm <NAME>`):

| Name | Class | Use for |
| --- | --- | --- |
| `logic-v2` | `LogicV2` | Screening. Rule-based, explainable, multi-script name matching. |
| `ofac` | `OFACMatcher` | Screening, when parity with OFAC's Sanctions List Search is required. |
| `er-unstable` | `EntityResolveRegression` | Deduplication, e.g. in `nk xref`. Not for regulated screening. |
| `regression-v1` | `RegressionV1` | Legacy regression model, the default for `nk match`. |
| `logic-v1` | `LogicV1` | Superseded by `logic-v2`. |
| `name-based` | `NameMatcher` | Deprecated in favor of `ofac`. |
| `name-qualified` | `NameQualifiedMatcher` | Deprecated in favor of `ofac`. |

Prefer `logic-v2` for screening and `er-unstable` for deduplication. The module exposes these choices as the constants `DefaultAlgorithm` (`regression-v1`, kept for API compatibility) and `DedupeAlgorithm` (`er-unstable`).

To score a pair of entities in Python, look up an algorithm by name and call its `compare` class method:

```python
from nomenklatura.matching import get_algorithm, ScoringConfig

algorithm = get_algorithm("logic-v2")
config = ScoringConfig.defaults()
result = algorithm.compare(query, candidate, config)
print(result.score, result.explanations)
```

## Interface

::: nomenklatura.matching.get_algorithm

::: nomenklatura.matching.ScoringAlgorithm

::: nomenklatura.matching.ScoringConfig

::: nomenklatura.matching.types.MatchingResult

::: nomenklatura.matching.types.FeatureResult

## Algorithms

::: nomenklatura.matching.LogicV2

::: nomenklatura.matching.OFACMatcher

::: nomenklatura.matching.EntityResolveRegression

::: nomenklatura.matching.RegressionV1

::: nomenklatura.matching.LogicV1

::: nomenklatura.matching.NameMatcher

::: nomenklatura.matching.NameQualifiedMatcher
