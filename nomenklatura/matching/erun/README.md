# `er-unstable`

`er-unstable` is the packaged entity-resolution regression model used for
dedupe-style matching. The model is intentionally simple: feature functions
encode a pair of entities into a fixed numeric vector, then a scikit-learn
pipeline scales those features and fits logistic regression probabilities.

The important part of this package is the training data pipeline. The raw pair
file contains source-derived judgements, repeated observations, already-resolved
canonical IDs, and a small number of irreconcilable labels. The training code
therefore treats the model-observable pair content as the unit of training and
evaluation, not the raw row and not the entity IDs.

## Input data

The raw pair file is produced by the `matcher_training` generator in the
OpenSanctions repository (`contrib/matcher_training/`). Its `DATA.md` — copied
next to every generated `pairs.jsonl` — documents the data semantics and must
be read before changing this pipeline. Each row carries, beyond the entity
pair and judgement: `left_cluster`/`right_cluster` (the sides' final
positive-only resolver clusters, the split unit), a hashed decider identity
(`user`), and provenance metadata. `unsure` judgements are dropped here.

## Training data identity

Canonical entity IDs are not source-record identities. Equal IDs often mean two
records from different sources have already been resolved into the same entity.
They are useful data, but they must not be used to decide whether two training
rows are duplicates.

The pipeline defines a snapshot as the ordered pair of:

- left schema and properties;
- right schema and properties.

Canonical IDs are deliberately excluded. The snapshot is ordered because the
feature encoder is not assumed to be perfectly symmetric for every feature.

Rows with identical snapshots provide identical observable evidence to the
model. They are grouped before splitting. A group with one label becomes one
training/evaluation example with a frequency count. A group with conflicting
positive and negative labels is quarantined, because no model using the current
inputs can learn both labels for the same observable pair.

Two further row-level filters apply before grouping:

- a non-positive pair whose sides share one positive cluster is a resolver
  self-contradiction and is skipped;
- a pair whose two clusters fall in different split partitions is discarded —
  the price of a leakage-free split (see below).

## Prepared dataset layout

Build a prepared dataset from raw judgement pairs with:

```bash
python -m nomenklatura.matching.erun.build \
  data/pairs-erun.json data/erun-prepared
```

or via:

```bash
make prepare-erun
```

The output directory is one dataset bundle:

- `manifest.jsonl`: one clean snapshot group per row, with schema, label,
  source frequency, logic-judgement count, representative raw row, partition,
  and development flag;
- `quarantine.jsonl`: snapshots excluded for conflicting labels
  (`reason: labels`) or for straddling the split (`reason: partitions`);
- `summary.json`: raw scan, grouping, quarantine, split, and development counts;
- `features.npy`: memory-mapped feature matrix;
- `labels.npy`: binary labels aligned to `features.npy`;
- `weights.npy`: source-row frequency for each snapshot group;
- `logic_counts.npy`: how many of each group's rows were judged by the
  rule-based `zavod/logic` decider — provenance for weighting experiments;
- `schemata.npy`: schema code for each row;
- `partitions.npy`: grouped train/test assignment;
- `development.npy`: deterministic development-subset membership;
- `row_numbers.npy`: representative raw row numbers for error analysis;
- `snapshots.npy`: snapshot digests;
- `cache.json`: cache metadata, feature names, manifest hash, and encoder
  signature;
- `build.json`: combined build and verification report.

The feature cache is invalidated when the feature order or implementation
changes. Loading checks the feature names and a source signature covering the
`erun` package.

## Splitting and evaluation

Train/test assignment happens at resolver-cluster level. Each cluster label is
assigned to a partition by a stateless seeded hash; a pair is kept only when
both of its sides fall in the same partition, so no cluster's evidence ever
appears on both sides of the split. Correlated near-duplicate pairs about the
same entity — which snapshot-level splitting cannot keep apart — land together
by construction. Cross-partition pairs are discarded and counted
(`skipped_cross_partition`); identical snapshots observed in both partitions
are quarantined (`reason: partitions`).

The development subset is also deterministic and stratified by schema and
label. It exists for quick iteration and should predict the direction of a
candidate feature change before the full grouped holdout is used.

Evaluation reports two views:

- grouped metrics: one vote per distinct observable snapshot;
- frequency-weighted metrics: repeated source observations counted by their
  raw frequency.

Grouped metrics are the primary model-quality signal because they avoid letting
repeated identical evidence dominate the estimate. Frequency-weighted metrics
remain useful as a secondary view — the frequency measures how often a pattern
was judged (replay multiplicity), not how often it occurs in source data.

One artifact of the cluster split to keep in mind when reading metrics: the
test partition is positives-enriched relative to train. A positive pair
survives with the cluster's partition probability, but a cross-cluster
negative needs both clusters on the same side, which suppresses negatives
quadratically. Comparing two models on the same test partition is fair;
absolute calibration numbers reflect the shifted prior, not production
traffic.

Evaluate a trained artifact or the packaged model with:

```bash
python -m nomenklatura.matching.erun.evaluate \
  data/erun-prepared --model data/erun-prepared/full-grouped.pkl
```

Omit `--model` to evaluate the packaged `er-unstable.pkl`.

## Training

Train from a prepared cache with:

```bash
python -m nomenklatura.matching.erun.train \
  data/erun-prepared data/erun-prepared/full-grouped.pkl --weight-mode grouped
```

or via:

```bash
make train-erun
```

The default training mode gives each clean snapshot group one vote. Frequency
weighting is available through `--weight-mode frequency`, but grouped training
is the primary choice because the model score is a probability over evidence
patterns, not over duplicated raw rows.

The fitted artifact contains:

- the scikit-learn pipeline;
- feature coefficients;
- training metadata and counts.

The package CLI command `nomenklatura train-erun-matcher` still accepts a raw
pairs file, but internally it builds a prepared dataset first and trains from
the grouped cache.

## Feature design constraints

Features should encode evidence in a bounded, interpretable way whenever
possible. Large magnitudes from repeated source history are usually a data-shape
artifact, not stronger evidence.

Address-number evidence is split into two bounded features:

- `address_number_overlap`: shared numbers divided by the smaller number set;
- `address_number_disagreement`: symmetric difference divided by the union.

If either side lacks address numbers, both features return zero. This separates
missing evidence from explicit disagreement and prevents a long address history
from creating unbounded positive or negative signal.

When changing features:

- keep feature functions deterministic;
- preserve cache invalidation by feature order and source signature;
- test boundedness and symmetry where the matcher expects symmetric evidence;
- compare candidates on the development subset before using the full grouped
  holdout;
- inspect per-schema metrics, not just aggregate quality.

## Known data characteristics

The raw pair file is not a balanced benchmark. It is a source-derived training
set with a high positive rate and many repeated evidence patterns. Precision at
common thresholds can look very high because the evaluation candidate
distribution is not the same as arbitrary production search traffic.

Useful model-quality signals are therefore:

- log loss and Brier score for probability calibration;
- ROC AUC and average precision for ranking;
- explicit threshold precision/recall;
- per-schema grouped metrics;
- disagreement between grouped and frequency-weighted views.

Some high-confidence apparent model errors are label or provenance issues rather
than feature failures. Exact-snapshot contradictions are quarantined
automatically; other suspicious rows should be reviewed through representative
row numbers and source provenance before adding features that merely overfit
bad labels.
