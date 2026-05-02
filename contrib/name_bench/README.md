# name_bench: harness for the name-distance comparator

A test harness for iterating on logic_v2's name-distance scoring.
Loads labelled name pairs from `cases.csv`, runs them through a
comparator, and prints a confusion matrix sliced by case group and
category. Sister to `entity_bench/` (which exercises the full
matcher on whole-entity records via `checks.yml`); this one stays
at the level of `(name1, name2)` pairs.

## Files

- `cases.csv` — labelled name-pair test set, schema documented
  below. **Source of truth.** Hand-edit to add cases, fix
  labels, refine categories.
- `run.py` — accuracy harness. Two modes (mutually exclusive):
  - `-c <comparator>` runs a named comparator over `cases.csv`,
    stores the per-case result in `run_data/`, and prints the
    summary.
  - `-s <run.csv>` re-renders the summary from a stored run
    CSV. Useful for re-thresholding (`-t 0.85`) and comparing
    runs without re-executing.
- `perf.py` — perf harness. Times each comparator across N
  runs of `cases.csv`, prints an apples-to-apples scoreboard
  (F1 + μs mean/p50/p95) plus a top-N% slowest-cases
  leaderboard per comparator. Useful for tracking the perf
  effect of matcher / primitive changes and surfacing
  pathologically slow inputs.
- `run_data/` — per-case dumps from `-c` runs. Timestamped
  by default; `--frozen` writes a stable `<comparator>-frozen.csv`.
  Timestamped runs are gitignored; `*-frozen.csv` is committed.

## Comparators

| Name | What it runs |
|---|---|
| `levenshtein` | naive Levenshtein similarity over casefolded strings — the unconditional floor |
| `logicv2` | `nomenklatura.matching.logic_v2.LogicV2.compare` on a synthesised single-property entity pair. The reference; freeze via `--frozen`. |

## Running

```bash
# from the nomenklatura repo root

# Run a comparator, store + summarise.
python contrib/name_bench/run.py -c logicv2

# Re-summarise a stored run at a tighter threshold.
python contrib/name_bench/run.py \
    -s contrib/name_bench/run_data/logicv2-20260501-104607.csv \
    -t 0.85

# Run quietly (just dump, no console summary).
python contrib/name_bench/run.py -c logicv2 --quiet

# Re-freeze the logic_v2 reference (rare — only when logic_v2
# changes upstream).
python contrib/name_bench/run.py -c logicv2 --frozen

# Diff a new run against the frozen logic_v2 reference.
qsv diff \
    contrib/name_bench/run_data/logicv2-frozen.csv \
    contrib/name_bench/run_data/logicv2-20260501-104607.csv

# Time all comparators (10 runs per case).
python contrib/name_bench/perf.py

# Time only one comparator with a longer run.
python contrib/name_bench/perf.py -c logicv2 --runs 100

# Show the top 10% slowest cases.
python contrib/name_bench/perf.py --top-slow-pct 10
```

Adding a new comparator: drop a new module under
`comparators/` defining a `Callable[[str, str, str], float]`,
import it in `comparators/__init__.py`, register in
`COMPARATORS`. Each iteration is one new entry.

## Schema (v1)

`cases.csv` columns:

| Column       | Required | Notes |
|--------------|----------|-------|
| `case_group` | yes      | Source/corpus tag (`nk_checks`, `nk_unit_tests`, `synth_companies`, `synth_corp_positives`, `synth_people`, …). |
| `schema`     | yes      | FtM schema name. Drives `analyze_names`'s `NameTypeTag`. Currently used: Person, Company, Organization, LegalEntity, Vessel. |
| `name1`      | yes      | Query-side name. Single string; analyze_names infers tags. |
| `name2`      | yes      | Result-side name. |
| `is_match`   | yes      | `true` / `false`. Ground-truth label. |
| `quality`    | optional | `STRONG` / `MEDIUM` / `WEAK`; blank → `MEDIUM`. Strength of evidence for the labelled outcome. See below. |
| `category`   | optional | Mutation/heuristic class for slicing reports. Blank if unlabelled. |
| `notes`      | optional | Free-text human-readable comment. Used for traceback to source tests, etc. |

`case_id` is **derived, not stored** — `run.py` computes a stable
8-char blake2b digest over `(case_group, schema, name1, name2)` at
load time. The harness emits it into per-case dump CSVs so `qsv diff`
between runs still works. This means cases.csv is hand-editable
without case_id management — drop a row in anywhere, save, run.
Duplicate `(case_group, schema, name1, name2)` tuples are flagged
with a stderr warning at load.

### `quality` — strength of evidence for the labelled outcome

Three tiers, applied symmetrically to matches and non-matches:

- **STRONG** — clearly true. Both label and outcome are unambiguous;
  the matcher *must* get this right. Typos in long words, identical
  strings, clean cross-script transliteration on common entities.
  STRONG-tier failures get their own leaderboard in the run summary
  and should be treated as P0 bugs.
- **MEDIUM** — clearly true with some structural nuance. Most cases
  default here. A failure is a regression worth investigating but
  not a P0.
- **WEAK** — borderline; the label is more tiebreaker than fact.
  Nicknames, gender variants, sibling-fund cases, single-char
  brand-stem swaps. Tolerated to fail on the verdict; expected to
  land in the score band near the threshold.

Defaults to MEDIUM when blank. Labelling is incremental — only
hand-tag cases at the obvious extremes (STRONG / WEAK); everything
else can stay MEDIUM. The run summary reports per-quality F1 and a
**calibration check**: mean scores should walk monotonically from
STRONG match → MEDIUM match → WEAK match → WEAK non-match → MEDIUM
non-match → STRONG non-match. Inversions or ties between adjacent
tiers indicate score-curve mis-calibration.

### v2 (deferred)

Will extend with optional tagged-name-part columns
(`name1_first`, `name1_last`, `name1_middle`, …) for cases
where input is structured — modelling the well-tagged
customer-record scenario (KYC at onboarding). Add new sources
under their own `case_group`.

## Adding cases

Edit `cases.csv` directly. The file is the canonical record;
no build step regenerates it. To bring in cases from a new
external source, write a one-shot script that emits rows in
the schema above and append them. Don't keep that script in
the repo unless re-running it makes sense (most ports are
write-once).

When adding rows manually:

- Pick a unique `case_id` within the group (zero-padded
  integer is fine).
- Pick a `case_group` for the source. New groups don't need
  registration; the harness slices by whatever values appear.
- For ambiguous ground-truth (component-test scores diverge
  from full-matcher verdicts, gendered-variant pairs), prefer
  the full-matcher reading. When in doubt, leave the case out.

## Inspecting `cases.csv` with qsv

`qsv` (CLI CSV tool) is installed locally. Useful queries:

```bash
# row counts and column list
qsv count   contrib/name_bench/cases.csv
qsv headers contrib/name_bench/cases.csv

# distribution by case_group, schema, is_match
qsv frequency -s case_group,schema,is_match contrib/name_bench/cases.csv | qsv table

# all labelled categories (skip blanks)
qsv search -s category '\S' contrib/name_bench/cases.csv \
    | qsv frequency -s category --limit 0 \
    | qsv table

# pretty-print a row range
qsv slice -s 100 -e 110 contrib/name_bench/cases.csv | qsv table

# all Vessel cases
qsv search -s schema 'Vessel' contrib/name_bench/cases.csv | qsv table

# all positive-match cases involving non-ASCII
qsv search -s name1 '[^\x00-\x7f]' contrib/name_bench/cases.csv \
    | qsv search -s is_match 'true' \
    | qsv table

# diff per-case output between two iteration runs
qsv diff iteration_a.csv iteration_b.csv
```

`qsv pivot` and `qsv sqlp` aren't in the local build; for
crosstabs use `qsv frequency` on multiple columns, or process
post-hoc.

## Sources

- `nk_checks` (226 rows) — ported from
  `contrib/entity_bench/checks.yml`. The full-matcher's
  regression test set, repurposed for name-distance evaluation.
  `category` carries the original YAML `label` field where
  present, blank otherwise.
- `nk_unit_tests` (84 rows) — ported from
  `nomenklatura/tests/matching/`. Two sub-sources:
  - 27 cases from the `CASES` list in `test_logic_v2_cases.py`
    — full-matcher tests with explicit `matches: bool` ground
    truth. `category=logic_v2_cases`.
  - 57 hand-curated cases derived from per-component tests in
    `test_names.py`, `test_logic_v2_names.py`, and
    `test_name_based.py`. Each was translated from a
    score-threshold assertion (e.g. JW > 0.9, Levenshtein <
    0.7) into an unambiguous `(name1, name2, is_match)`
    triple. Cases with gendered-variant ambiguity (e.g.
    Michel/Michelle) were excluded — the per-component score
    and the full-matcher verdict can disagree, and
    `nk_checks` already records those. `notes` carries the
    originating test function; `category` groups by sub-test
    (e.g. `friedrich_fps`, `obama_tps`).

Planned additions:

- `qarin_negatives` / `un_sc_positives` / `us_congress` —
  port from
  `yente/contrib/candidate_generation_benchmark/fixtures/`.
