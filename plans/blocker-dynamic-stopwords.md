---
description: Plan to replace blocker field-percentile stopwords with token-keyed dynamic cutoffs based on estimated pair-generation cost.
date: 2026-07-02
tags: [nomenklatura, blocker, duckdb, stopwords, xref, memory]
---

# Dynamic blocker stopwords

## Context

The blocker currently removes high-frequency tokens using per-field percentile
heuristics. That makes the safety property indirect: the code removes "the top
N% of tokens in this field" rather than "tokens whose blocks are too expensive
to materialize".

The desired replacement is a single stopword implementation based on estimated
candidate-pair cost. Field-specific percentile stopwords should be removed, not
kept as a second filtering layer.

The existing blocker acceptance criteria emphasize bounded pair generation,
noise control, deterministic output, and observability. This plan applies those
requirements to the current DuckDB blocker by making high-cardinality token
removal explicit and measurable.

## Current finding

Tokens are now prefixed by source/type (`c:`, `np:`, `sy:`, `a:`, `n:`, etc.).
In the two inspected DuckDB indexes, no token value appears under more than one
`field`.

That means `token` can be treated as the stopword key. `field` should remain in
stats/logging as diagnostic metadata, but stopword joins and grouping should use
`token` as the identity.

## Validation data

### `/Users/pudo/tmp/index.duckdb`

This was the failing small coalition sanctions run with stopwords disabled.

```text
entries:             1,851,586 token rows
entities:               89,063
distinct tokens:        378,614
stopwords:                    0
naive pair cost:         ~1.53B
compatible pair cost:    ~1.16B
```

The pair cost is highly concentrated:

```text
top 1 token:     50% of naive estimated pair rows
top 8 tokens:    75%
top 110 tokens:  90%
top 258 tokens:  95%
top 1017 tokens: 99%
```

Worst token:

```text
c:ru  df=41,931  naive_cost=879M  compatible_cost=564M
```

Schema-compatible dynamic thresholds over raw `entries`:

```text
max token cost  stopped tokens  kept compatible cost  max kept df
1,000           3,252           2.9M                  68
2,000           2,453           4.1M                  96
5,000           1,763           6.2M                  145
10,000          1,371           9.0M                  195
100,000           450           39.6M                 577
```

### `/Users/pudo/tmp/index_other.duckdb`

This larger DB already had the old static stopwords applied.

```text
entries:             9,369,533 token rows
entities:              640,988
distinct tokens:      2,250,228
old stopwords:           36,763
entries_filtered:     3,620,936 token rows
```

The old implementation removed:

```text
naive pair cost removed:        ~15.84B
naive pair cost kept:           ~9.9M
compatible pair cost kept:      ~9.8M
max kept df:                    61
max kept token compatible cost:  1,830
```

Raw pair cost is again concentrated:

```text
top 2 tokens:    50% of naive estimated pair rows
top 23 tokens:   75%
top 198 tokens:  90%
top 515 tokens:  95%
top 2808 tokens: 99%
```

Worst tokens:

```text
c:fr      df=120,139  naive_cost=7.22B  compatible_cost=4.14B
c:us      df=60,800   naive_cost=1.85B  compatible_cost=1.75B
np:mayor  df=42,311   naive_cost=895M   compatible_cost=892M
```

Schema-compatible dynamic thresholds over raw `entries`:

```text
max token cost  stopped tokens  kept compatible cost  max kept df
1,000           17,310          13.8M                 63
2,000           13,393          19.3M                 90
5,000            9,131          33.0M                 137
10,000           6,864          49.0M                 192
100,000          2,209          204.7M                538
```

## Proposed behavior

Create token statistics from raw `entries` and mark stopwords when a token's
estimated schema-compatible pair contribution exceeds a configured cap.

The primary stopword rule:

```text
stop token if compatible_pair_cost > max_token_pair_cost
```

Default:

```text
max_token_pair_cost = 2,000
```

This is close to the largest token block kept by the old implementation in the
larger sample, while keeping far fewer arbitrary low-cost tokens out of the
index. `10,000` is the first alternate comparison point if validation shows the
default is too aggressive on recall; it keeps materially more tokens but still
removes the pathological blocks in both sample DBs.

## Table shape

Replace the current `tokens` and `stopwords` meaning with token-keyed stats:

```sql
CREATE OR REPLACE TABLE token_stats (
    token TEXT,
    field TEXT,
    freq HUGEINT,
    df HUGEINT,
    compatible_pair_cost HUGEINT,
    stopword BOOLEAN
);

CREATE OR REPLACE TABLE stopwords AS
SELECT token, field, freq, df, compatible_pair_cost
FROM token_stats
WHERE stopword;
```

`stopwords.token` is the key. `field` is diagnostic only.

## Pair-cost calculation

Use schema-compatible cost rather than plain `df choose 2`, because the pair
query already filters through `schemata`. The plain document-frequency estimate
is useful for logs and sanity checks, but the filtering rule should match the
actual pair-generation shape as closely as practical.

Sketch:

```sql
CREATE OR REPLACE TABLE token_schema_counts AS
SELECT
    token,
    any_value(field) AS field,
    schema,
    count(*) AS df,
    sum("count") AS freq
FROM entries
GROUP BY token, schema;

CREATE OR REPLACE TABLE schema_pairs AS
SELECT DISTINCT
    least("left", "right") AS left_schema,
    greatest("left", "right") AS right_schema
FROM schemata;

CREATE OR REPLACE TABLE token_stats AS
WITH compatible AS (
    SELECT
        l.token,
        sum(
            CASE
                WHEN l.schema = r.schema THEN
                    cast(l.df * (l.df - 1) / 2 AS HUGEINT)
                ELSE
                    cast(l.df * r.df AS HUGEINT)
            END
        ) AS compatible_pair_cost
    FROM token_schema_counts AS l
    JOIN token_schema_counts AS r
        ON l.token = r.token
       AND l.schema <= r.schema
    JOIN schema_pairs AS s
        ON s.left_schema = l.schema
       AND s.right_schema = r.schema
    GROUP BY l.token
),
totals AS (
    SELECT
        token,
        any_value(field) AS field,
        sum(freq) AS freq,
        sum(df) AS df
    FROM token_schema_counts
    GROUP BY token
)
SELECT
    totals.token,
    totals.field,
    totals.freq,
    totals.df,
    ifnull(compatible.compatible_pair_cost, 0) AS compatible_pair_cost,
    ifnull(compatible.compatible_pair_cost, 0) > ? AS stopword
FROM totals
LEFT JOIN compatible ON compatible.token = totals.token;
```

The normalized `schema_pairs` table avoids double-counting reciprocal schema
compatibility rows. The calculation is still an estimate of the join workload,
but it matched the observed filtered index shape well in the larger sample.

## Code changes

1. Remove `DEFAULT_STOPWORDS_PCT`, `DEFAULT_FIELD_STOPWORDS_PCT`,
   `stopwords_pct`, and `build_field_stopwords`.
2. Replace `_build_stopwords()` with a token-stat build that computes
   schema-compatible pair cost and fills `stopwords` from the configured cap.
3. Make `_apply_stopwords()` join only on `token`.
4. Replace `disable_stopwords` with the dynamic implementation. Scope configs
   should no longer need `disable_stopwords`; if the old option is still passed,
   log a warning or raise a clear configuration error during the migration.
5. Add an index-build log summarizing:
   - indexed entity count;
   - raw token rows;
   - distinct tokens;
   - stopped token count;
   - kept/stopped estimated compatible pair cost;
   - max kept token cost and max kept `df`;
   - top stopped tokens by compatible pair cost.

## Suggested configuration

Keep the public knob small:

```yaml
blocker_options:
  max_token_pair_cost: 2000
```

Optional later knobs, only if real scopes need them:

```yaml
blocker_options:
  max_token_pair_cost: 10000
  log_top_stopwords: 25
```

Do not add per-field percentages back. If a field needs special treatment, first
check whether tokenization should be changed instead.

## Tests

Unit tests:

- a token with compatible pair cost exactly equal to the cap is kept;
- a token with compatible pair cost above the cap is stopped;
- `stopwords.token` is sufficient to filter `entries`;
- the filter does not depend on field-specific percentiles;
- schema-compatible cost counts same-schema blocks as `n * (n - 1) / 2`;
- schema-compatible cost counts cross-schema compatible blocks once;
- high-cardinality common tokens are removed while specific duplicate evidence
  remains available.

Fixture tests:

- existing blocker fixture pairs are still found;
- pair order remains deterministic;
- obvious false-positive pairs sharing only stopped tokens are absent;
- `match_entities()` uses the same token-keyed stopwords.

Scale validation:

- run the blocker on the two inspected DB-derived scopes or equivalent rebuilt
  stores with `max_token_pair_cost=2,000`;
- record index build time, pair generation time, peak RSS, stopped/kept pair-cost
  stats, and xref yield;
- repeat with `10,000` only if the first run appears too aggressive on recall.

Per the pacing rule, benchmark or parity disappointment is a checkpoint: report
the measured number before tuning further.

## Migration notes

Before merging the implementation, remove `disable_stopwords: true` from scope
configs that were using it to bypass the old percentile logic.

The old `tokens` table was frequency-oriented and grouped by `(field, token)`.
The replacement `token_stats` table should be token-oriented and should support
diagnosis of pair-cost behavior. Any external diagnostic SQL that expects the
old table shape may need to query `token_stats` instead.

## Open questions

- Should a future global budget stop additional tokens when the sum of kept
  compatible pair cost exceeds a configured limit, or is the per-token cap
  sufficient once real xref runs are measured?
