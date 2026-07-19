---
description: Reorganize matcher tests to mirror their source modules while preserving matcher-local behavioral contracts and intentional duplication.
date: 2026-07-19
tags: [nomenklatura, matching, tests, organization, independence]
---

# Organize matcher tests by source module

## Goal

Make ownership of every matcher test obvious from its path and filename. The test
tree should mirror `nomenklatura/matching`, and a mixed test file should be split
according to the module whose behavior each test asserts.

Matcher implementations are intended to remain independently understandable and
stable. Tests that express a useful contract for more than one matcher should
therefore be copied into the relevant matcher suites, with matcher-specific
expectations, rather than hidden behind one parametrized cross-matcher test.

This is a test-only reorganization. It should not change matcher code, scoring
behavior, fixtures, or coverage expectations.

## Ownership rules

1. Mirror source package paths beneath `tests/matching/`. For example,
   `nomenklatura/matching/logic_v1/identifiers.py` is tested by
   `tests/matching/logic_v1/test_identifiers.py`.
2. Name the primary test file `test_<module>.py`. If one source module needs
   several substantial suites, use `test_<module>_<behavior>.py`, such as
   `test_model_cases.py` and `test_model_ranking.py`.
3. Assign a test according to the production function or class whose result it
   asserts. Imports used only for entity construction, configuration, types, or
   test data do not give a second module ownership of the test.
4. Split a test that directly asserts behavior from multiple production modules.
   Do not leave a mixed test in a family-level catch-all file.
5. Keep only genuinely generic test construction helpers shared. Rename the
   current `tests/matching/util.py` entity factory to
   `tests/matching/factory.py` so it cannot be mistaken for tests of
   `nomenklatura.matching.util`.
6. Keep model-level composition tests even when their underlying feature
   functions have focused unit tests. A feature test protects the primitive; a
   model test protects that matcher's selection, weighting, and explanation of
   the feature.
7. Do not centralize matcher contract cases into a fixture that parametrizes all
   matcher classes. Copy the small number of important cases into each applicable
   matcher directory so a matcher suite can be read, run, and changed on its own.

## Proposed layout and moves

### Shared comparison primitives

Create `tests/matching/compare/` and move the already focused suites without
changing their assertions:

- `test_addresses.py` -> `compare/test_addresses.py`
- `test_countries.py` -> `compare/test_countries.py`
- `test_dates.py` -> `compare/test_dates.py`
- `test_gender.py` -> `compare/test_gender.py`
- `test_identifiers.py` -> `compare/test_identifiers.py`
- `test_names.py` -> `compare/test_names.py`

`test_compat.py` remains at `tests/matching/test_compat.py`, matching
`matching/compat.py`. Add focused `test_pairs.py`, `test_types.py`, or
`test_util.py` only if tests for those modules already exist elsewhere; do not
invent new coverage as part of the move.

### `logic_v1`

Create `tests/matching/logic_v1/`:

- Move model scoring, overrides, qualifier progression, and entity-level
  comparison tests from `test_logic_v1.py` to `test_model.py`.
- Move `test_phonetic`, `test_person_name_phonetic_match`, and the phonetic parts
  of the single-name/alphabet cases from `test_logic_v1.py` to
  `test_phonetic.py`.
- Keep assertions for `compare.names.person_name_jaro_winkler` in
  `compare/test_names.py`; where a case intentionally checks both phonetic and
  Jaro-Winkler behavior, copy the relevant inputs into both module suites rather
  than retaining a mixed test.
- Move `test_logic_v1_identifiers.py` to `logic_v1/test_identifiers.py`.
- Move `test_logic_v1_multi.py` to `logic_v1/test_multi.py`.

The resulting `logic_v1/test_model.py` must import `LogicV1` from its defining
module, not from the aggregate `nomenklatura.matching` export, so module ownership
is explicit.

### `logic_v2`

Create `tests/matching/logic_v2/` and
`tests/matching/logic_v2/names/`:

- Move the boolean scenario matrix from `test_logic_v2_cases.py` to
  `logic_v2/test_model_cases.py`.
- Move ranking comparisons from `test_logic_v2_pairs.py` to
  `logic_v2/test_model_ranking.py`.
- Move configuration behavior from `test_logic_v2_config.py` to
  `logic_v2/test_model_config.py`.
- Move `test_logic_v2_identifiers.py` to
  `logic_v2/test_identifiers.py`.
- Move `test_logic_v2_analysis.py` to
  `logic_v2/names/test_analysis.py`.
- Move `test_logic_v2_distance.py` to
  `logic_v2/names/test_distance.py`.
- Split `test_logic_v2_names.py`: `entity_names` assertions belong in
  `names/test_analysis.py`, while `name_match` assertions belong in
  `names/test_match.py`.

Keep the three model suites separate because the source `model.py` has a large
behavioral surface and the suffixes state which aspect is under test. Consolidate
their duplicated entity-building code locally only if doing so does not make the
suite depend on another matcher directory.

### `name_based`

Create `tests/matching/name_based/`:

- Split `test_name_based.py` into `test_model.py` for `NameMatcher` and
  `NameQualifiedMatcher`, `test_names.py` for `jaro_name_parts` and
  `soundex_name_parts`, and `test_misc.py` for `orgid_disjoint`.
- Split `test_ofac.py`: direct `ofac_name_score` behavior belongs in
  `test_ofac.py`; `OFACMatcher.compare` and qualifier/weight integration belong
  in `test_model.py`.

This split is important even though `OFACMatcher` is implemented using
`ofac_name_score`: the former tests the matcher contract, while the latter tests
the scoring primitive.

### `regression_v1`

Create `tests/matching/regression_v1/` and move
`test_regression_v1.py` to `test_model.py`. Keep its entity examples in that
matcher directory. The current suite only asserts `RegressionV1` model behavior,
so no split is required.

Do not add tests for `names.py`, `misc.py`, `train.py`, or `util.py` during the
reorganization. Record those untested modules as follow-up coverage gaps rather
than mixing coverage expansion into a path-only change.

### `erun`

Retain `tests/matching/erun/`, but align filenames with modules:

- Rename `test_address_features.py` to `test_misc.py`; both tests directly assert
  address-number features defined in `erun/misc.py`.
- Rename `test_prepare.py` to `test_train.py`; its asserted operations are
  defined in `erun/train.py`. `EntityResolveRegression` and `JudgedPair` are test
  collaborators, not additional owners.

As with `regression_v1`, list currently untested feature modules (`countries.py`,
`dob.py`, `identifiers.py`, `names.py`, and model behavior not reached by the
training tests) separately. Do not create superficial tests merely to fill every
source filename.

## Independent matcher contracts

During the move, identify existing examples that encode broad matcher guarantees,
especially:

- exact same-name entities produce the matcher's strongest expected result;
- a close name variant scores below an exact match;
- conflicting dates, countries, or identifiers reduce the score when that
  matcher claims to use them;
- a strong matching identifier can rescue a weak or missing name where supported;
- ranking cases prefer the candidate with consistent qualifiers;
- configuration overrides affect only the matcher that owns them.

Preserve or copy these cases into each applicable matcher's model suite. Expectations
may differ by matcher and should be written explicitly in each copy. Do not require
parity between matchers, and do not use inheritance or a common parametrized case
table that couples their behavior.

The reorganization should initially duplicate only cases already represented in
the suite. Any proposal to add new behavioral coverage is a separate checkpoint,
because new assertions can expose or redefine matcher semantics.

## Execution checkpoints

### Checkpoint 1: shared primitives and test helpers

Move the `compare` tests and rename the entity factory. Run only the affected
tests, then the full `tests/matching` suite. Stop and report any collection,
parity, or correctness failure before continuing.

### Checkpoint 2: heuristic matcher families

Reorganize `logic_v1`, `logic_v2`, and `name_based`, splitting mixed tests by the
ownership rules above. Preserve test bodies before considering deduplication or
new cases. Run each matcher directory independently, then run all matcher tests.
Stop and report any failure.

### Checkpoint 3: regression matcher families

Reorganize `regression_v1` and `erun`. Run each directory independently, then run
all matcher tests. Stop and report any failure.

### Checkpoint 4: contract audit

Compare the model suites for the broad guarantees above. Report which existing
cases were intentionally copied, which were matcher-specific, and which coverage
gaps remain. Get confirmation before adding new cases or changing production
code.

## Verification and acceptance criteria

- Every matcher test path identifies the production package and module it owns.
- No test function directly asserts unrelated production modules.
- Mixed files (`test_logic_v1.py`, `test_logic_v2_names.py`,
  `test_name_based.py`, and `test_ofac.py`) have been split as described.
- Each matcher directory can be run independently with pytest.
- Intentional duplicated contracts are local to matcher directories and have
  matcher-specific expected results.
- Generic helpers contain no matcher-specific cases or expectations.
- Test count is unchanged except for explicitly approved duplicated cases.
- The complete matcher suite passes with the same production code and test data.
- `git diff --check` is clean, and the final diff contains only test-tree changes
  unless a scope expansion is separately approved.

## Coverage expansion

Add independent behavioral coverage for the two regression matchers without
pinning serialized model probabilities or loading fixtures from `contrib/` at
test time.

1. Cover the public feature and training-helper modules in `regression_v1`.
2. Cover the country, date, identifier, name, and remaining miscellaneous
   features in `erun`.
3. Give both model suites copied contract cases inspired by the entity and name
   benchmarks: exact versus typo versus unrelated names, company legal-form
   variants, qualifier conflicts, and identifier rescue. Use relative scores;
   additionally require symmetry from the erun dedupe matcher.

Run each matcher directory after its feature tests are added. Add the model
contracts only after both feature suites pass, then run all matcher tests. Any
failed intended contract is a stop-and-report point: do not tune or retrain a
matcher as part of the coverage change.
