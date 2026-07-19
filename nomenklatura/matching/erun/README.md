# `er-unstable` training

`er-unstable` is a logistic-regression matcher trained from the judgement pairs
produced by `contrib/matcher_training` in the OpenSanctions repository. Read the
`DATA.md` shipped beside `pairs.jsonl` before changing the consumer: it is the
source of truth for replay, identity, provenance, and exclusion semantics.

The nomenklatura trainer makes five consumer decisions:

1. Drop `unsure` judgements and invalid, non-matchable, or address pairs.
2. Hash final positive-cluster labels into a deterministic 70/30 train/test
   split and discard pairs whose sides cross the split.
3. Drop non-positive pairs whose sides belong to the same positive cluster.
4. Group identical ordered entity snapshots without using canonical IDs, then
   exclude groups with conflicting labels or occurrences in both partitions.
5. Give each remaining snapshot group one vote. Replay multiplicity is not
   treated as source frequency, and `zavod/logic` rows receive no special
   weighting.

Training is intentionally one linear operation:

```bash
nomenklatura train-erun-matcher data/pairs-erun.json
```

The input is scanned twice: once to select groups and once to encode only their
representative rows. The command fits on the train partition, prints grouped
aggregate and per-schema holdout metrics, and writes the packaged model.

The cluster split enriches the test partition for positives because a negative
pair survives only when both clusters hash to the same side. Its metrics compare
models consistently, but its positive rate does not represent production
traffic.
