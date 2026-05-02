---
description: Research notes on OFAC's public Sanctions List Search tool — its algorithm, score semantics, data model (incl. weak/strong alias regime), and compliance posture — captured as input to the nomenklatura name-matcher refactor. Companion to rigour/plans/name-screening.md.
date: 2026-05-01
tags: [nomenklatura, matching, names, screening, sanctions, ofac, research]
---

# OFAC name matcher — research notes

A working notebook for building a nomenklatura matcher that
**substantially emulates** OFAC's public Sanctions List Search
tool — not a "good" matcher in the academic-accuracy sense, but
one whose hits and approximate scores reproduce what a customer
would see if they ran the same query on
`sanctionssearch.ofac.treas.gov`.

The OFAC tool is widely understood to be permissive and noisy
by modern standards (see prior art and false-positive evidence
below). That is the spec. We are not trying to fix it; we are
trying to reproduce its behavior in a controllable, testable,
explainable form so that:

- Customers can self-serve "what would the OFAC tool say about
  this name?" without round-tripping to treasury.gov.
- Compliance documentation can cite a deterministic algorithm
  whose behavior tracks the public regulator tool, rather than
  defending divergence from it.
- We have a reproducible parity-test target — fixtures of
  (query, expected hits, expected approximate score) — to
  regress against as OFAC's tool changes.

The "good" matcher (`logic_v2`, configurable bias, designed
for the FP/recall trade-offs in `name-screening.md`) is a
separate algorithm that already exists. The OFAC emulator
is its own `ScoringAlgorithm`, registered alongside
`RegressionV1`, `LogicV2`, etc.

Companion documents:

- `rigour/plans/name-screening.md` — industry context (KYC vs.
  payment screening, threshold bands, FP baseline, score-curve
  shape). Explains why our **default** matcher diverges from
  OFAC; this document explains why a **separate** algorithm
  should not.
- `rigour/plans/weighted-distance.md` — residue distance
  primitive used by the good matcher; mostly orthogonal here.
- `nomenklatura/matching/logic_v2/names/match.py` — current
  default matcher.
- `nomenklatura/matching/__init__.py` — algorithm registry
  where the OFAC emulator slots in.

## Status — final algorithm

**A 70-line emulator that tracks OFAC within ±5 points on 95.7% of a
164-row fixture, mean absolute error 1.5.** Lives in
`nomenklatura/contrib/ofac2021/algo.py`:

```python
def ofac_score(query: str, candidate: str) -> int:
    return round(max(_t1(query, candidate),
                     _t2(query, candidate)) * 100)
```

The fingerprint of the OFAC algorithm is three reverse-engineered
quirks plus one **forensic find** about which Jaro-Winkler
implementation OFAC's contractor likely used in 2008-2012.

### The forensic find — SimMetrics-style Jaro-Winkler

OFAC's tool is ASP.NET WebForms with `__VIEWSTATE`,
`__doPostBack`, and `Sys.Extended.UI.SliderBehavior` from the
**AjaxControlToolkit** — a Microsoft-released library that peaked
2007-2012 on .NET Framework 3.5/4.0. Server is hidden behind an F5
BIG-IP, but the front-end stack is unmistakably late-2000s/early-
2010s federal Microsoft. The 2021 algorithm upgrade likely modified
the matching service but kept the WebForms front-end.

In that era, a .NET dev needing Jaro-Winkler had three options:
roll their own from the 1990 paper, use **SimMetrics.NET** (the
.NET port of Sam Chapman's Java SimMetrics, the canonical academic
similarity library of the era), or buy IBM Global Name Recognition.
The FAQ's plain naming of "Jaro-Winkler and Soundex" rules out the
black-box commercial libs — leaving SimMetrics or hand-rolled.

**The behavioural difference that matters:** Winkler's 1990 paper
recommends applying the prefix bonus only when pure Jaro ≥ 0.7
(the "boost threshold"). Modern Python libs honour this — rapidfuzz,
jellyfish, and py_stringmatching all skip the bonus below 0.7.
**SimMetrics-Java does not.** It applies the prefix bonus
unconditionally.

For long-candidate cases where pure Jaro sits in the 0.6–0.7 band:

| Pair | pure Jaro | rapidfuzz JW | SimMetrics-style | OFAC |
|---|---:|---:|---:|---:|
| VLADIMIR PUTIN ↔ VLADIMIROV NIKOLAI… | 0.683 | 0.683 | **0.810** | 0.84 |
| GEORGE BUSH ↔ GEORGIEVA ELENA… | 0.668 | 0.668 | **0.801** | 0.83 |
| VLADIMIR PUTIN ↔ VLADIMIROVKA AWRC | 0.638 | 0.638 | **0.783** | 0.82 |

Switching to SimMetrics-style JW (12 lines: pure Jaro + manual
prefix bonus, no threshold check) is the single biggest accuracy
gain in the whole reverse-engineering effort. It collapsed the
"long-candidate gap" entirely — under-predictions dropped from 7 to
2 across the fixture, mean |Δ| from 1.73 to 1.49.

### The other three quirks

These come from the empirical fixture:

1. **Whole-string JW gated by `input[0] == candidate[0]`** (literal,
   not per-token, not letter-set). The `BUSH GEORGE` query returns
   0 hits while `GEORGE BUSH` returns 3 — same tokens, reversed
   order. Implement the gate on the typed string's first character;
   do not normalise it away.

2. **Per-input-token best-pairing JW with a 0.5 floor.**
   `GEORGE BUSH ↔ HASWANI, George` scores 50 in OFAC. A simple
   mean of best pair scores gives 73; zeroing pairs below 0.5
   (BUSH↔HASWANI = 0.46) before the mean gives `(1.0 + 0) / 2 = 0.5`
   — exactly OFAC's reported score. The floor is the soft "first-
   letter check" the FAQ alludes to — implicit in JW magnitude,
   not an explicit letter-level gate.

3. **Drop input tokens of ≤2 chars (with single-token protection).**
   `KIM JONG UN` matches `KIM, Jong Sik / Jong Man / Jung Jong / Yo
   Jong` all at 100 — only achievable if the 2-char input "UN" is
   dropped before the per-token mean. Single-char queries like `Z`
   keep their lone token (the safety clause).

### Empirical results (164 positive + 6 negative fixtures)

```
                  mean Δ    mean |Δ|   within ±5    over+5    under−5    FP
faq249_d2          −0.1       2.47       145         9         10        1/6
faq249_thr         −0.8       1.95       150         4         10        1/6
faq249_trunc       −0.3       1.73       152         5          7        1/6
faq249_simjw       −0.1       1.49       157         5          2        1/6   ← shipped
```

- **95.7% of positive fixtures within ±5 points** of OFAC's reported score.
- **Mean absolute error 1.49 points** (on a 0-100 scale).
- **5 of 6 negatives** correctly score below the 80 slider — the
  one false positive (`ALQAEDA → AL QAEDA = 92`) is a tokenisation
  edge case documented below.

### Things we tried that didn't work

- **moov-io's length-ratio penalty (PR #116)**: J-W × min/max
  length ratio. Disproved on the fixture (mean |Δ| 6.9, much worse
  than baseline). OFAC isn't doing this.
- **Candidate truncation at >2× length ratio.** Approximated the
  SimMetrics-no-threshold effect crudely — recovered 152/164 within
  ±5 by capping the candidate at input length, but is mechanically
  unprincipled. Replaced by the SimMetrics JW which gets 157/164
  without the truncation hack.
- **Soundex 1.0 bridge** on per-pair scoring (`max(JW, 1.0 if codes
  equal)`). Too aggressive — `PATINO ↔ PUTIN` both Soundex P350,
  saturating to score 100. The 0.85-floor variant is gentler but
  adds nothing measurable over plain JW.
- **Per-pair first-letter filter** (each input token's pair partner
  must share its first letter). Fixes the HASWANI cluster but
  breaks `PUTIN ↔ TURIN` and `PABLO ↔ ESCOBAR` cases where OFAC
  clearly matches across letters when JW is high. Replaced by the
  JW < 0.5 floor.
- **Standard Soundex / Metaphone bridging across spellings**
  (`MAHMUD` ↔ `MAHMOOD` both M530). Phonetic codes match, but
  cross-spelling pairs are already JW ≈ 0.91 — high enough to
  clear the 0.5 floor, so phonetic equivalence adds nothing.

### Known remaining limitations

1. **Alias-aware scoring** is missing. OFAC scores a query against
   the *best* of an entity's aliases; this function scores against
   one alias-string at a time. `PABLO ESCOBAR ↔ ESCOBAR GAVIRIA`
   scores 82 (model) vs 90 (OFAC) because OFAC likely matched
   against some other alias of Roberto Escobar containing "PABLO".
   Fixing requires SDN_ADVANCED.XML alias data.
2. **`ALQAEDA → AL QAEDA = 92` (model) vs <80 (OFAC).** A
   tokenisation edge case where joined-form input matches a
   multi-token candidate via T1 even though OFAC apparently
   filters it. The mechanism isn't recovered.
3. **Long-candidate sub-cluster `GEORGE BUSH ↔ GE-something
   noise`** (GEYE Aroun, GEO HIT, GHORB NOOH). Model under-predicts
   by 6–10 points; OFAC is more permissive in the 60–76 band than
   our model. Not load-bearing — well below the 80 slider.

### Why this matters / blog-post pitch

OFAC's tool is the canonical sanctions-screening reference, used by
banks and compliance teams worldwide, and OFAC explicitly declines
to recommend a threshold (FAQ 250) — pushing the calibration burden
onto the user. Customers regularly ask us "why does your score
differ from sanctionssearch?". Until now we explained: "different
algorithm, different shape." Now we can say: "we reproduce it within
1.5 points on average, here's the algorithm in 70 lines."

The forensic step — figuring out *which* Jaro-Winkler the contractor
used — was the unlock. Modern open-source projects trying to
reproduce OFAC (moov-io, kyc-agent, compliance-core) all picked up
the threshold-respecting variant from their language's standard
library and stopped there. None of them reach OFAC parity. The
delta is one historical flag in a 1990 paper that the canonical
academic library of the era happened to ignore.

The fixture lives in `nomenklatura/contrib/ofac2021/fixtures.csv`;
re-capture on each SDN list update is the maintenance burden.

---

## TL;DR for the emulator

1. **Goal is parity, not quality.** "Reproduces OFAC behavior
   on the SDN list" beats "produces good name matches." If
   OFAC ranks a poor match high, we rank it high.
2. **The algorithm is documented but underspecified.**
   Jaro-Winkler + Soundex, run as (a) whole-string J-W and (b)
   per-name-part J-W∪Soundex with an **unspecified**
   composite-across-parts aggregator. Score is `max(a, b)`,
   gated by a first-letter / 50%-edit-distance blocker (FAQs
   247, 249, verified). The composite-across-parts step and
   any 2021 third algorithm are the reverse-engineering
   targets.
3. **Score is name-only on 0–100.** Address, ID, DOB, country,
   type are hard filters on the candidate set, not features in
   the score (FAQ 251). Our emulator should mirror this even
   though our default matcher does not.
4. **Naive Jaro-Winkler does not reproduce OFAC's behavior.**
   moov-io/watchman demonstrated this concretely in 2019: a
   straight J-W implementation returned `George Bush → George
   Habbash @ 89%`, where OFAC at the same threshold returned
   nothing. Their fix was to multiply J-W by a length-ratio
   penalty, which got closer but did not reach parity. This is
   the central calibration problem.
5. **Weak vs. strong aliases is regulator-blessed (FAQ 124).**
   Whether the public OFAC tool actually demotes weak AKAs in
   its search ranking is unconfirmed — needs empirical check.
   The data carries the flag (`LowQuality` in
   `SDN_ADVANCED.XML`); the question is whether the search UI
   uses it.
6. **The data model is in `SDN_ADVANCED.XML`.** Typed name
   parts, multi-script aliases, `LowQuality` flag, structured
   IDs, partial DOBs — all the structure the search UI hides
   but the algorithm presumably uses. Our emulator must ingest
   this, not legacy SDN.xml.
7. **OFAC's matching vendor is undisclosed.** Some inputs
   to the algorithm (the composite-across-parts aggregator,
   the 2021 third algorithm) cannot be definitively recovered
   from public sources. The emulator will be a behavioral
   approximation, not a code-equivalent reimplementation.
8. **Build a parity test fixture early.** A few dozen
   `(query → ranked hits + scores)` triples scraped from the
   live tool become the regression suite. Without this we
   have no way to know whether we are converging.

## The Sanctions List Search tool

Lives at `https://sanctionssearch.ofac.treas.gov/`. Free,
public, web-only. Covers all OFAC-administered lists in one
search — SDN plus every Non-SDN list (SSI, FSE, Non-SDN Iran,
PLC, NS-CMIC, etc.).

The same underlying data is published as machine-readable feeds
at `sanctionslist.ofac.treas.gov` in a stack of formats from
legacy fixed-width through the modern `SDN_ADVANCED.XML` and
`CONS_ADVANCED.XML`. The tool and the feeds share data; only
the tool ships an algorithm.

### Inputs and what scores

Per FAQ 246, **only the Name field invokes fuzzy logic**.
Per FAQ 251, **only the name field influences the Score**.
Everything else — Address, City, State, Country, ZIP, Type
(Individual / Entity / Vessel / Aircraft), Program, List, ID#
— is plain character-match filtering on the candidate set.

The score the user sees is a name-string score. Other inputs
narrow what was matched against; they don't reweight.

### Score and threshold

- Range **0–100**, 100 = exact.
- Slider defaults to **100** (FAQ 248). Lowering reveals
  fuzzier results.
- **No recommended threshold.** FAQ 250: "each search has its
  own unique set of facts… users… must make their own match
  threshold determinations based upon their own internal risk
  assessments and established compliance practices."
- No per-component score breakdown, no explanation of which
  alias matched, no exported audit trail beyond a printable
  result page.

The "no recommended threshold" stance is load-bearing for the
broader compliance posture: OFAC declines to bless a number,
which means no institution can defend a missed hit by saying
"we used the threshold the regulator told us to." The
calibration obligation is permanent and program-specific.

## The algorithm (FAQs 247, 249)

Wording from FAQs 247 and 249 verified against OFAC directly
(see Sources). FAQ 249 was last released 28 April 2021, post-
dating the January 2021 algorithm upgrade — so it describes
the current state.

**Pre-filter (FAQ 249).** Candidates are first restricted to
those whose first letter matches the input's first letter
**and** that are at least 50% similar by edit distance. Edit
distance is defined in the FAQ as "the minimum number of
operations required to transform the input string of
characters into the string that it is being compared to on
the list." This is a blocking step, not a scoring step.

**Two algorithms.** Jaro-Winkler (string difference) and
Soundex (phonetic).

**Two techniques run in parallel:**

1. **Whole-string Jaro-Winkler.** Input compared to each full
   name on the lists.
2. **Per-name-part decomposition.** Input split into name
   parts ("John Doe" → "John", "Doe"). Each part compared to
   name parts on the lists using **both** Jaro-Winkler and
   Soundex. The technique produces both a score per name part
   **and a composite score across all name parts entered**.
   FAQ 249 does not specify how the composite is formed.

The reported Score is the **higher** of the two technique
scores (FAQ 249, verbatim: "returns the higher of the two
scores in the Score column").

**FAQ 252 / third-algorithm claim.** A January 2021
recent-actions notice announced an algorithmic upgrade for
"resource efficiency". A secondary source (Comsure) reports
that a third algorithm was added in addition to Jaro-Winkler
and Soundex. The current FAQ 249 wording (released 28 April
2021, post-upgrade) describes only the two algorithms — so
either the third was internal-only, or the FAQ was not
updated to reflect it, or the Comsure summary overstated.
This is not load-bearing for the refactor; flagging for
completeness.

### What this implies, mechanically

- **Composite-across-parts is unspecified.** FAQ 249 says
  technique 2 produces both per-part scores and a composite
  across all parts, but does not say how the composite is
  formed (max? mean? Hungarian assignment? length-weighted
  average?). Without that detail we can't reproduce the score
  exactly even if we wanted to — and we don't.
- **Reported score is max(whole-string JW, per-part composite),
  not a blend.** A short input matched well against a long
  target's surname can carry the score even if the rest is
  unmatched. This is the opposite of what
  `name-screening.md` argues we should do for legal-entity
  matching: unmatched `LOCATION` / `ORG_CLASS` / qualifier
  tokens are evidence of a different entity, not noise to
  discount.
- **Soundex is English-phonetic.** Cross-script and
  cross-language phonetic equivalence is not modelled.
  Multi-script coverage relies entirely on the underlying list
  carrying transliterated aliases; if it doesn't, the algorithm
  doesn't bridge the gap.
- **Max-of-techniques** lets a single strong part-level match
  pull the whole score up. Generous on short queries; noisy
  on long ones.
- **First-letter pre-filter** is a hard recall ceiling on
  inputs whose transliteration changes the leading character
  (Russian Х → Kh / H, Arabic ع → none / a, etc.). This is a
  real failure mode; our blocking does not have this constraint
  and we should keep it that way.

## Hit triage — FAQ 5

The OFAC-blessed checklist for distinguishing a "valuable hit"
from a false positive, in order:

1. Confirm the hit is actually against an OFAC-administered
   list.
2. Assess hit quality — type mismatches (vessel vs. individual)
   are immediate disqualifiers.
3. Assess **how much** of the listed entry's name matched —
   full match vs. last name only.
4. Compare every available data point: full name, address,
   nationality, passport / tax ID / cedula, place of birth,
   DOB, former names, aliases.
5. Tally similarities and weigh them.

This is qualitative and human-driven. There is no numeric
cutoff in FAQ 5 and OFAC consistently frames the human
assessment as the decision point. Our matcher already produces
a numeric score; the FAQ-5-style human assessment is what the
threshold band 0.5–0.85 in `name-screening.md` is feeding into.

## Weak vs. strong aliases (FAQs 122–124)

**Weak AKA.** A relatively broad or generic alias likely to
generate large volumes of false hits in screening. OFAC keeps
them on the list because the target is in fact known by them
— but flags them so screeners know not to fire on them in
isolation.

**Strong AKA.** Default; not specifically marked.

**FAQ 124, paraphrased:** OFAC does not expect screeners to
treat weak AKAs as standalone triggers. They are intended to
help **confirm or deny** a hit raised by other identifiers.
This is the closest thing in OFAC's public corpus to a safe
harbor.

Encoding by format:

- Legacy SDN.txt / PDF: weak AKAs are **wrapped in double
  quotes**.
- DEL / FF / PIP / CSV: weak AKAs surface in the Remarks field
  with quotes.
- `SDN_ADVANCED.XML`: alias quality is a Boolean attribute on
  the alias element — `LowQuality="true"` (weak) vs. `false`
  (strong).

### Refactor implication

The matcher should respect the weak/strong distinction
explicitly. Concretely:

- Strong AKA matches feed normal scoring.
- Weak AKA matches should be gated — either down-weighted
  heavily or excluded from primary scoring and surfaced only
  as confirming evidence when a strong-AKA / primary-name
  match is also present.

We need to confirm the data path: does followthemoney /
zavod's OFAC importer currently preserve the `LowQuality`
flag from `SDN_ADVANCED.XML`? If not, that's a prerequisite
for any weak/strong logic in the matcher.

## The 50 Percent Rule

Briefly, since it isn't name matching: any entity 50%-or-more
owned (in the aggregate, directly or indirectly) by one or
more blocked persons is itself blocked, even if not on the
SDN list. Per FAQ 398 and the August 2014 revised guidance.

OFAC publishes no list of derivatively blocked entities;
screeners must compute the ownership graph themselves. The
public Sanctions List Search does **not** do this. Production
screening combines name matching with an ownership traversal;
nomenklatura already supports the data model for it via
followthemoney `Ownership` statements. Out of scope for the
matcher refactor itself but worth noting that the matcher's
output is an input to a downstream graph computation, not a
final compliance decision.

## Data model — SDN Advanced XML

The Advanced XML files (`SDN_ADVANCED.XML`,
`CONS_ADVANCED.XML`) conform to a UN-developed sanctions data
standard. They carry materially more structure than the legacy
flat formats:

- **Typed name parts.** Last name, first name, given name,
  patronymic, etc. — non-Western names decomposed rather than
  smushed into a single string. This is what enables
  language-aware matching against Advanced data.
- **Multi-script names.** A target can carry aliases in
  Cyrillic, Arabic, Chinese, etc., alongside Latin
  transliterations.
- **Alias quality.** `LowQuality` Boolean per alias.
- **Document quality.** Government IDs flagged legitimate vs.
  fraudulent.
- **Rich linked metadata** — addresses, identity documents,
  partial / range DOBs, places of birth, gender, nationality,
  programs, remarks — linked to the primary entry by UID.

The Advanced files publish in **parallel** with the legacy
formats; they don't replace them. Most recent schema-level
change was a namespace update in May 2024
(`recent-actions/20240507_44`).

The public Sanctions List Search exposes far less of this
richness than the data carries. That's a UI / engineering
choice on OFAC's part, not a data limitation. Our matcher,
operating on followthemoney entities derived from the
Advanced XML, has access to the full structure and should
use it.

## The vendor question

I could not find any public OFAC document, FOIA disclosure,
SAM.gov procurement record, or Federal Register notice that
identifies the matching engine vendor for the public
Sanctions List Search. The FAQs describe the algorithms only
generically (Jaro-Winkler, Soundex, an unnamed third).

Speculation that OFAC uses IBM Global Name Recognition (GNR),
SSA-NAME3 (formerly Search Software America), or
Refinitiv / World-Check is unsupported by anything I could
find in public sources. The published algorithm description
is consistent with a fairly conventional in-house
implementation — first-letter blocking, per-token Jaro-Winkler
+ Soundex, max-of-two — rather than a named commercial library.

A definitive answer would require a FOIA request for the
Sanctions List Search statement of work / contract.

What **is** publicly contracted is the SDN data publishing
pipeline — Sanctions List Service at
`ofac.treasury.gov/sanctions-list-service` — but that's the
data feed, not the matching engine.

We should stop using "OFAC uses X" claims in customer
conversations.

## Comparison: UK FCDO and EU

**UK** — As of 28 January 2026, the OFSI Consolidated List
closed and the **UK Sanctions List** at
`search-uk-sanctions-list.service.gov.uk` became the single
source. FCDO publishes a documented user guide with a
deterministic, simple fuzzy spec:

- Fuzzy off by default; checkbox toggle.
- 1–2 char query → no fuzzy.
- 3–4 char → 1 character different.
- 5+ char → up to 2 characters different.
- Double-quote forces exact.

This is essentially a Damerau-Levenshtein edit-distance
threshold by length. Far simpler than OFAC's Jaro-Winkler +
Soundex + tokenized hybrid. Matches are binary; no published
score.

**EU** — The Consolidated Financial Sanctions List is a data
feed (`webgate.ec.europa.eu/fsd/fsf`). The EU does not
publish a methodology document for fuzzy matching, and the
official Sanctions Map is a country-program lookup, not a
search service. EU institutions are expected to bring their
own screening engine.

The three regulators sit at three points on a transparency
gradient: UK most explicit and reproducible, OFAC documented
but harder to characterize end-to-end, EU silent. Our matcher
needs to be defensible to all three audiences; matching the UK
spec is mechanical, matching OFAC is impossible without
knowing the third 2021 algorithm, and matching the EU is
underdetermined.

## Prior art — open-source attempts at OFAC parity

A handful of OSS projects have tried to reproduce OFAC's
behavior. The useful one is moov-io/watchman; the others
mostly enumerate "Jaro-Winkler + a phonetic algo" without
demonstrating parity.

### moov-io/watchman (Go, since ~2019)

The longest-running open-source attempt at OFAC parity.
Issue [moov-io/watchman#115](https://github.com/moov-io/watchman/issues/115)
(2019) is the canonical demonstration that **a naive
Jaro-Winkler matcher does not reproduce OFAC behavior, even
at the same threshold**:

| Query        | moov match @ default | OFAC tool @ 80% |
|--------------|----------------------|-----------------|
| George Bush  | HABBASH, George 89%  | (no results)    |
| George Bush  | HASWANI, George 88%  | (no results)    |
| George Bush  | CHIWESHE, George 84% | (no results)    |

The fix in [moov-io/watchman PR #116](https://github.com/moov-io/watchman/pull/116)
("limit string similarity to their length ratio") multiplies
J-W by a length-ratio penalty. Post-fix, the same query
returned `HABBASH 0.74`, `HASWANI 0.74` — closer to OFAC's
"nothing at 80%" behavior, but still not at parity.

Lessons for us:

- **A length-ratio penalty is the cheapest first move.** It's
  the single biggest source of moov's pre-fix over-matching,
  and it's what Jaro-Winkler explicitly does *not* do. Our
  emulator should apply something equivalent — `J-W ×
  min(|a|, |b|) / max(|a|, |b|)` is moov's shape; worth
  trying first.
- **Even with the length-ratio fix, parity isn't reached.**
  Moov gets to 0.74 where OFAC returns nothing; OFAC's
  blocker (first-letter + 50% edit distance) is filtering
  candidates that moov scores then displays. The blocker is
  load-bearing for false-positive suppression.
- **The "George Bush" set is a known-good fixture.** Any
  reproduction of OFAC's behavior must return zero hits for
  "George Bush" at the 80% slider setting. Add to parity
  test suite.

Worth periodically re-checking moov-io's current matching
code as their convergence work continues.

### Other listed issues (light on substance)

- [jbillay/kyc-agent#19](https://github.com/jbillay/kyc-agent/issues/19)
  is a generic user story for a fuzzy matcher (J-W +
  Levenshtein + Soundex/Metaphone, 85% default). Not OFAC-
  specific. Useful as a sanity check on what people reach for
  by default; not useful for parity work.
- [lapc506/compliance-core#19](https://github.com/lapc506/compliance-core/issues/19)
  is a one-line stub: "Jaro-Winkler + Double Metaphone +
  DOB." Confirms the consensus open-source stack;
  contributes nothing to parity.

The pattern is clear: most OSS projects pick the algorithm
family OFAC names and stop there, without measuring whether
their results actually match OFAC's. moov is the exception,
and even moov has not declared parity.

## Empirical evidence from the live tool

Captured 2026-05-01 against
`https://sanctionssearch.ofac.treas.gov/`. The tool is an
ASP.NET WebForms app; submissions are POSTs preserving
`__VIEWSTATE` + `__VIEWSTATEGENERATOR` from a prior GET. No
event validation, no encrypted viewstate. Form fields:
`txtLastName` (the Name input), `Slider1` (score 50–100,
default 100), `ddlType`, `ddlList`, `ddlCountry`,
`lstPrograms`, plus address / city / state / ID. Slider
**minimum is 50** — the tool will not search below.

### Capture mechanism

A 30-line Python script (urllib + cookielib) does the GET,
extracts hidden inputs, POSTs the form. Working copy in
`/tmp/ofac_query.py` for now; productionise into
`nomenklatura/contrib/ofac_parity/capture.py` with the
fixture itself.

### Query: `VLADIMIR PUTIN`

**Slider = 100, default — 2 hits.** Both score 100.

| Score | Name |
|------:|---|
| 100 | PUTIN, Vladimir |
| 100 | PUTIN, Vladimir Vladimirovich |

Both link to the same SDN entity (`Details.aspx?id=35096`).
The second has an extra unmatched patronymic token; OFAC
still scores it 100.

**Implication.** The per-name-part technique returns a max
(or near-max) score when **all input tokens are matched**,
regardless of unmatched extra tokens on the candidate side.
This is the opposite of `name-screening.md`'s legal-entity
rule. For OFAC parity it's a hard requirement: extra
candidate tokens must not subtract from the score.

**Slider = 80 — 14 hits.** Selected rows:

| Score | Name | Type |
|------:|---|---|
| 100 | PUTIN, Vladimir | Individual |
| 100 | PUTIN, Vladimir Vladimirovich | Individual |
| 90 | VLADIMIR BILIY | Individual |
| 89 | VLADIMIR VINOGRADOV | Vessel |
| 88 | VLADIMIR ARSENYEV | Vessel |
| 88 | VLADIMIR LATYSHEV | Vessel |
| 88 | VLADIMIR MONOMAKH | Vessel |
| 88 | VLADIMIR TOCHMASH | Entity |
| 84 | VLADIMIROV, Nikolai Nikolayevich | Individual |
| 84 | VLADIMIROV, Nikolay Nikolayevich | Individual |
| 83 | VLADIMIROV, Vladimir Vladimirovich | Individual |
| 83 | VLADISLAV STRIZHOV | Vessel |
| 82 | VLADIMIROVKA ADVANCED WEAPONS AND RESEARCH COMPLEX | Entity |
| 81 | POLIN, Vladimir Anatolevich | Individual |

**Slider = 50 — 312 hits.** The algorithm's noise floor at
its widest setting.

### What the `VLADIMIR PUTIN` row teaches

1. **Shared first-name prefix dominates.** "VLADIMIR BILIY"
   gets 90 against "VLADIMIR PUTIN". Both 14 chars, length
   ratio 1.0, shared 9-char prefix "VLADIMIR ". The
   Winkler bonus on long shared prefixes pulls otherwise
   weak matches well over 80.
2. **Type is not a scoring feature.** A query that's
   obviously a person matches vessels and entities with
   high scores when nothing else discriminates. Type
   filtering is the user's responsibility via the
   `ddlType` dropdown.
3. **Patronymic / extra-token tolerance.** Both
   PUTIN-variants score 100; VLADIMIROV-variants score
   83–84 against VLADIMIR PUTIN despite different
   surnames. The matcher does not punish unmatched
   candidate tokens.
4. **Reverse name order works.** Input "VLADIMIR PUTIN"
   matches stored "PUTIN, Vladimir" at 100 — the
   tokenizer is order-insensitive at the per-name-part
   level, which is consistent with FAQ 249's described
   per-part comparison.

### Query: `GEORGE BUSH`

Captured to test the moov-io 2019 false-friend cases.

**Slider = 100 — 0 hits.**

**Slider = 80 — 3 hits:**

| Score | Name | Type |
|------:|---|---|
| 86 | GEORGIOU, Georgios | Individual |
| 85 | GEORGY MASLOV | Vessel |
| 83 | GEORGIEVA, Elena Aleksandrovna | Individual |

**None of the moov-io 2019 false friends** (HABBASH,
HASWANI, CHIWESHE) appear. Cross-checked individually:

- `HABBASH` query at slider 50 returns 29 hits, none with
  surname `HABBASH`. The PFLP leader has been **delisted**
  (he died 2008, list cleanup since).
- `HASWANI` query at slider 50 returns 635 hits including
  `HASWANI, George @ 100` and `HASWANI, Jurj @ 100`.
  **Still on the SDN** (PAARSSR-EO13894 program).
- `CHIWESHE` not material to the discussion either way.

So HASWANI is the test case: still listed, used to match
"George Bush" at 88 in moov-io 2019, and now does not match
"GEORGE BUSH" at all even at slider 80.

### A working algorithm model

The combined evidence — VLADIMIR PUTIN, GEORGE BUSH, and the
moov-io discrepancy — fits a specific shape of FAQ 249's
two-technique algorithm:

**Technique 1 (whole-string Jaro-Winkler):**
- The first-letter / 50%-edit-distance pre-filter applies
  **here**. If the first character of the input string
  doesn't match the first character of the candidate's full
  name, this technique scores 0 / contributes nothing.
- Otherwise standard Jaro-Winkler with the conventional
  4-character prefix-bonus cap.

**Technique 2 (per-name-part):**
- Tokenize input into parts and candidate into parts.
- For each input part, find its best Jaro-Winkler / Soundex
  match among candidate parts.
- Composite = **average over all input parts** (including
  parts that found no good match — they pull the average
  down). Does **not** divide only by matched parts.
- The pre-filter does **not** apply per-part; otherwise we
  couldn't get the VLADIMIR PUTIN ↔ PUTIN, Vladimir = 100
  result (input "V" vs candidate "P" at full-string).

**Reported score = max(technique 1, technique 2).** FAQ 249
verbatim.

This model explains every captured data point so far:

| Query | Candidate | T1 (whole) | T2 (per-part) | Max | OFAC |
|---|---|---|---|---|---|
| VLADIMIR PUTIN | PUTIN, Vladimir | filtered (V→P) | (1.0 + 1.0)/2 = 1.0 | 1.0 | 100 ✓ |
| VLADIMIR PUTIN | PUTIN, Vladimir Vladimirovich | filtered | (1.0 + 1.0)/2 = 1.0 | 1.0 | 100 ✓ |
| VLADIMIR PUTIN | VLADIMIR BILIY | J-W ≈ 0.89 | (1.0 + 0.4)/2 ≈ 0.70 | 0.89 | 90 ✓ |
| GEORGE BUSH | GEORGIOU, Georgios | J-W ≈ 0.86 | (0.87 + 0.4)/2 ≈ 0.64 | 0.86 | 86 ✓ |
| GEORGE BUSH | HASWANI, George | filtered (G→H) | (1.0 + 0.4)/2 = 0.70 | 0.70 | < 80 ✓ |

The HASWANI line is the load-bearing one. It's still on the
list, the 2019 moov-io report had it matching at 88 with
naive J-W, and OFAC's current algorithm scores it at ~70 —
**below** the 80 slider — because **technique 2's composite
is averaged over all input parts, and input "BUSH" pulls the
average down.** Technique 1 is filtered by the
first-letter pre-filter (G≠H).

### Revised understanding of moov-io's PR #116

moov's length-ratio penalty (`J-W × min/max length ratio`)
is a **different mechanism** from OFAC's apparent shape, but
it has a similar effect in many cases — both reduce scores
when the input and candidate are dissimilar in ways naive
J-W ignores. moov was directionally right but mechanically
different. For our parity work:

- **Don't copy moov's length-ratio fix.** It's a proxy for
  the wrong thing.
- **Implement the first-letter pre-filter at the
  whole-string level** as a hard gate on technique 1.
- **Implement the average-over-input-parts composite** for
  technique 2.
- **Take the max** as the reported score.

This is a reverse-engineered model from a small fixture; it
needs to be validated against more queries before being
treated as load-bearing.

### Other observed details

- **SDN list version** at capture: `4/30/2026 1:33:17 PM`.
  Non-SDN: `1/8/2026 10:05:51 AM`. Fixture must record
  the list date — same query against a different list
  version will return different hits.
- **Multiple SDN entries can dedupe to one entity** in the
  results list — both Putin name forms are entity 35096.
  Set agreement should compare entity IDs, not row
  count, to avoid double-counting aliases of the same
  target.

### Extended fixture — 12 more queries (slider 80)

All captured 2026-05-01, SDN list 4/30/2026. Stored
verbatim as initial parity-test fixtures. Only top hits
shown; full results in `/tmp/ofac_result_*_80.html` and
`/tmp/ofac_batch_results.json` (lift into
`nomenklatura/contrib/ofac_parity/` when productionising).

**`PUTIN`** (single token) — 15 hits across 12 entities:

| Score | Name |
|------:|---|
| 100 | PUTIN, Vladimir |
| 100 | PUTIN, Vladimir Vladimirovich |
| 97 | PUTINA, Anna Evgenyevna |
| 97 | PUTINA, Maria |
| 97 | PUTINA, Yekaterina |
| 90 | PUNTI, Pere |
| 88 | PTI |
| 85 | PATINO FOMEQUE, Victor Hugo |

Single-token input. T2 has only one input part. Single-edit
neighbors (PUTINA = +1 char) score 97. Substring-of-input
matches (PTI ⊂ PUTIN) still score 88 because of strong
shared P-prefix.

**`PUTIN VLADIMIR`** (order reversal of Putin's name) — 12 hits:

| Score | Name | Note |
|------:|---|---|
| 100 | PUTIN, Vladimir | exact (with comma normalised) |
| 100 | PUTIN, Vladimir Vladimirovich | extra patronymic free |
| 92 | TURIN, Vladimir | **predicted by model: (JW(PUTIN,TURIN)≈0.84 + 1.0)/2 = 0.92** ✓ |
| 89 | PUTINA, Maria | T1 wins via shared "PUTIN" prefix |
| 88 | TJRURIN, Vladimir | T2 ≈ (0.75 + 1.0)/2 = 0.875 ✓ |
| 88 | TYURINE, Vladimir | same shape as TJRURIN ✓ |

The TURIN, Vladimir hit is the cleanest model-fit data
point: T2 average over input parts predicts 92, OFAC reports
92.

**`VLADIMR PUTIN`** (typo: missing I in VLADIMIR) — 13 hits:

| Score | Name |
|------:|---|
| 99 | PUTIN, Vladimir |
| 99 | PUTIN, Vladimir Vladimirovich |
| 87 | VLADIMIR ARSENYEV |
| 87 | VLADIMIR MONOMAKH |
| 86 | VLADIMIR BILIY |

Single missing-character typo on a 7-char token barely
moves the score (99 vs 100). T2 best pairing for VLADIMR
vs Vladimir is ~0.99.

**`VLADIMIR PUTNI`** (typo: transposition in PUTIN) — 13 hits:

| Score | Name |
|------:|---|
| 98 | PUTIN, Vladimir |
| 98 | PUTIN, Vladimir Vladimirovich |
| 90 | VLADIMIR BILIY |
| 88 | VLADIMIR ARSENYEV |

Transposition typo on the surname → 98. Note that VLADIMIR
BILIY scores 90 against `VLADIMIR PUTNI` — same as it scored
against `VLADIMIR PUTIN`. Confirms **whole-string J-W is
prefix-dominated and largely indifferent to suffix
content**, the load-bearing weakness of the algorithm.

**`PUTIN VLADIMIROVICH`** (patronymic only, no first name) — 14 hits:

| Score | Name |
|------:|---|
| 100 | PUTIN, Vladimir Vladimirovich |
| 97 | PUTIN, Vladimir |
| 86 | POTANIN, Vladimir Olegovich |
| 86 | PUTILIN, Dmitry Sergeyevich |
| 86 | PUTINA, Maria |

Patronymic-without-first-name still hits the canonical Putin
entry at 100 because all input parts find perfect candidate
counterparts.

**`Владимир Путин`** (Cyrillic) — **0 hits**.

Confirms FAQ-aligned behavior: **OFAC's tool does no input
transliteration.** Cross-script coverage relies entirely on
the SDN list carrying transliterated aliases.

**`OSAMA BIN LADEN`** — 6 hits, 3 entities:

| Score | Name | Entity |
|------:|---|---|
| 100 | BIN LADEN, Osama | 6365 |
| 97 | BIN LADIN, Osama | 6365 |
| 97 | BIN LADIN, Osama bin Muhammad bin Awad | 6365 |
| 84 | OSAMA TRADING COMPANY LTD | 18536 |
| 84 | USAMA BIN LADEN NETWORK | 6366 |

Three-token input with one transliteration (LADEN) hits the
Latinised variant at 100 and the official-list spelling
(LADIN) at 97. Entity 6365 = OBL himself; entity 6366 = his
network organisation.

**`USAMA BIN LADIN`** (canonical SDN spelling) — 5 hits, 2 entities:

| Score | Name | Entity |
|------:|---|---|
| 100 | BIN LADIN, Usama | 6365 |
| 100 | BIN LADIN, Usama bin Muhammad bin Awad | 6365 |
| 97 | BIN LADEN, Usama | 6365 |
| 97 | USAMA BIN LADEN NETWORK | 6366 |
| 97 | USAMA BIN LADEN ORGANIZATION | 6366 |

Note: same sanctioned target, three different name forms in
the list, three different scores (100/97). The matcher
treats each list entry as a separate candidate. Set
agreement on entity ID is the right metric, not row count.

**`KIM JONG UN`** — 72 hits, 42 entities. Top:

| Score | Name |
|------:|---|
| 100 | KIM, Jong Un |
| 100 | KIM, Jong Man |
| 100 | KIM, Jong Sik |
| 100 | KIM, Jung Jong |
| 100 | KIM, Yo Jong |
| 93 | KIM, Song Hun |
| 92 | KIL, Jong Hun |
| 91 | KIM, So'ng-hun |

**Model-breaking case.** Five distinct individuals all score
100. The simple "average over input parts" composite would
predict different scores for each (e.g. KIM, Jong Man should
be lower because UN ≠ Man). Hypotheses to test:

1. **Short tokens (≤2 chars) get heavily de-weighted or
   dropped** before composite. With "UN" treated as
   negligible, input becomes [KIM, JONG] and all five
   candidates have perfect 2-token matches.
2. **Composite is max-of-best-pairings**, not average. But
   this contradicts GEORGE BUSH → HASWANI, George being
   filtered (max would give 1.0).
3. **First-letter normalisation interacts with token
   length** in a way we haven't recovered.

Hypothesis 1 is the working theory. Tests to disambiguate:
queries with deliberately short non-meaningful tokens
("PUTIN A", "PUTIN II"), and queries where the short token
is meaningful ("KIM IL SUNG").

**`MOHAMMED ALI`** — 628 hits, 319 entities. Top hits all
at 100 (twelve different individuals, all containing some
form of Mohammed and Ali in their name). Common-name
explosion in raw form. Confirms that **OFAC's tool ships no
common-name penalty**; the precision-leaning customer must
filter downstream by DOB, nationality, etc.

**`BUSH GEORGE`** (reverse of GEORGE BUSH) — **0 hits.**

Compare to GEORGE BUSH which had 3 hits (GEORGIOU, GEORGY,
GEORGIEVA) at 86/85/83. Same input tokens, reversed order,
zero hits.

**This is the smoking-gun for the asymmetric T1
first-letter gate.** With BUSH leading the input, T1's
first-letter check rejects all G-prefixed candidates. T2
still runs but produces composite ≈ 0.64 (avg of
GEORGE→Georgios=0.87 and BUSH→GEORGIOU=0.4), below the 80
slider threshold.

The asymmetry tells us:

- T1 keys on `input[0] == candidate[0]`, where both are the
  first character of the **whole input string** as the user
  typed it — not a normalised letter set, not the first
  character of each token.
- The user-supplied token order matters in a way that
  contradicts what FAQ 249 implies (it suggests
  per-name-part comparison should be order-insensitive).
  T2 is order-insensitive at the per-part level, but T1's
  contribution depends on string order.
- A user querying "Putin Vladimir" gets different results
  from "Vladimir Putin" — confirmed in the data:
  `VLADIMIR PUTIN` returned 14 hits at slider 80,
  `PUTIN VLADIMIR` returned 12. Different sets, same
  intent.

**Implication for the emulator:** the first-letter gate is
hard-coded to the input's first character. Implement it
literally; do not "fix" it.

**`JOHN SMITH`** — 4 hits:

| Score | Name |
|------:|---|
| 85 | JOHN, Damien |
| 85 | JOHN, Damion |
| 84 | JOHN, Damion Patrick |
| 81 | Johnny Hood |

No "Smith" entity rises above 80 against this query.
"JOHN, Damien" wins via T1 (J=J ✓, shared "JOHN " prefix
producing whole-string J-W ≈ 0.85). T2 composite would be
~0.7 (JOHN-John 1.0, SMITH-Damien ~0.4). T1 dominates.

The total absence of Smith hits is a useful negative case:
the SDN list either contains no notable Smiths matching
this query, or any that exist score below 80 because the
other tokens drag the composite down.

### Arabic-naming stress test — 14 queries

Captured 2026-05-01 against same SDN list. The Arabic
naming patterns (transliteration variants, particle
prefixes, hyphenated compound names) stress the model in
ways the European-name fixture didn't.

**`MAHMOOD AHMED BASHIR-UD-DIN`** — 25 hits. The truly
sanctioned person (entity 7133) appears **three times** at
ranks 2, 5, 13 with three different alias forms. **Rank 1 is
a different sanctioned person:**

| Rank | Score | Name | Entity |
|---:|---:|---|---:|
| 1 | 92 | MAHMOOD, Fariduddin | 45129 |
| 2 | 90 | MAHMOOD, Sultan Bashiruddin | **7133** |
| 3 | 90 | MAHMOUD, Sheikh Farid-ud-Den | 45129 |
| 4 | 89 | MAHMOOD, Shahid | 21284 |
| 5 | 89 | MAHMOOD, Sultan Bashir-Ud-Din | **7133** |
| 13 | 86 | MEHMOOD, Dr. Bashir Uddin | **7133** |

This is **the canonical example of why ranking by score is
insufficient for screening.** The user typed the
sanctioned individual's full name with the canonical
hyphenated transliteration. The matcher returned a
different sanctioned individual (Fariduddin) at the top
spot at 92, ahead of the right person at 90.

Why? Whole-string J-W (T1) prefers compact candidates with
clean "MAHMOOD … …UDDIN" prefix-and-suffix structure, and
penalises the longer "MAHMOOD, Sultan Bashir-Ud-Din" form
through Jaro's character-window mechanic. The 6-character
"Sultan" in the middle pushes the right-person form below
the shorter "Fariduddin" form despite Fariduddin being a
totally different name.

This is OFAC's algorithm doing exactly what its docs say it
does. For the emulator: replicate this. For customer
support: this is why screening tools need to surface the
top-N entities (not the top-N rows) and why analyst review
can never be replaced by a score alone.

**`BASHIR-UD-DIN` alone** → 32 hits, top hit
`MAHMOOD, Sultan Bashir-Ud-Din @ 100`. The right person
gets the top spot when the user queries the **distinctive**
part of the name. The full-name query is worse than the
distinctive-part query — counter-intuitive.

**Hyphen behaviour.** Three forms of the same compound
produce nearly identical results:

- `BASHIR-UD-DIN` → top: `Bashir-Ud-Din @ 100`, 32 hits
- `BASHIR UD DIN` → top: `Bashir-Ud-Din @ 100`, 41 hits
- `BASHIRUDDIN` → top: `Bashiruddin @ 100`, 24 hits

The hyphenated and space-separated queries return overlapping
result sets. The joined-form query returns a different,
smaller set. **Conclusion: hyphens normalise to spaces; the
joined form is treated as a single token.** This matches
the AL-QAEDA / AL QAEDA / ALQAEDA evidence below.

**`AL-QAEDA` / `AL QAEDA` / `ALQAEDA`:**

- `AL-QAEDA` → 47 hits, `AL QAEDA @ 100` top.
- `AL QAEDA` → 44 hits, same top hit.
- `ALQAEDA` → 16 hits, top score **91**, **no 100s.** The
  SDN list never carries the joined form; the joined-form
  query falls back to fuzzy partial matches.

Hyphen-to-space normalisation is now load-bearing in the
model. Implement it explicitly in the input pre-processing
step.

**MAHMUD vs MAHMOOD transliteration.** Both spellings exist
on the SDN list as separate entries. They cross-match at
~86 but not at 100:

- `MAHMUD` → 549 hits, top all 100 (matches MAHMUD-spelled).
- `MAHMOOD` → 190 hits, top all 100 (matches MAHMOOD-spelled).
- `MAHMUD AHMAD BASHIRUDDIN` → top 90, no 100s. The
  MAHMOOD-spelled version of the right person scores 86,
  not 100. **Soundex (both = M530) does not fully bridge the
  spelling gap** in OFAC's composite — supports our earlier
  hypothesis that the per-part score is character-J-W
  dominant, with Soundex contributing weakly if at all.

**ABDUL RAHMAN vs ABDULRAHMAN.** The list carries both
joined and separated forms as separate entries (different
sanctioned individuals).

- `ABDUL RAHMAN` → 225 hits all top-100.
- `ABDULRAHMAN` → 505 hits all top-100.
- `ABD AL RAHMAN` → 148 hits all top-100, including
  apostrophe forms like `'ABD AL-RAHMAN`.

Apostrophes are normalised away (or treated as token
separators); `ABD AL RAHMAN` matches `'ABD AL-RAHMAN` at
100.

### Implications for emulator pre-processing

The input normalisation pipeline before tokenisation:

1. Uppercase.
2. Strip / replace with space: hyphens, apostrophes, commas,
   parentheses, periods. (Probably all non-alphanumerics
   except space.)
3. Collapse multiple spaces.
4. Tokenise on space.

Soundex contribution to the per-part composite is small or
nil based on observed cross-spelling behavior. Implement
Soundex per FAQ 249 wording but expect the parity tests to
be insensitive to whether it actually fires.

Common-name explosion is built-in:

- `MAHMUD` → 549 results all top-100.
- `ABDULRAHMAN` → 505 results all top-100.
- `MOHAMMED ALI` → 628 results all top-100.

The emulator inherits this and we should not try to add a
common-name penalty (`name-screening.md`'s argument for one
applies to the *good* matcher, not this one).

### Updated working algorithm model

The 5 + 12 = 17 captured queries support this model with
one known gap (short-token weighting, see KIM JONG UN):

```
def ofac_score(input_str, candidate_str):
    # Normalise: uppercase, replace non-alphanumerics
    # (hyphens, apostrophes, commas, etc.) with space,
    # collapse multiple spaces. Confirmed by AL-QAEDA /
    # AL QAEDA equivalence and BASHIR-UD-DIN / BASHIR UD DIN
    # equivalence.
    q = normalise(input_str)
    c = normalise(candidate_str)

    # Technique 1: whole-string Jaro-Winkler, gated.
    if q[0] == c[0] and edit_distance_ratio(q, c) >= 0.5:
        t1 = jaro_winkler(q, c)
    else:
        t1 = 0.0

    # Technique 2: per-name-part composite. No first-letter gate.
    q_parts = tokenise(q)
    c_parts = tokenise(c)
    # TODO(short-token weighting): KIM JONG UN evidence
    # suggests very short tokens (≤2 chars) are de-weighted
    # or dropped. Validate with targeted queries.
    pair_scores = best_pairing_jw_or_soundex(q_parts, c_parts)
    t2 = mean(pair_scores)  # one entry per input part

    return max(t1, t2)
```

Open empirical questions tracked against this model:

- Short-token weighting (KIM JONG UN @ 100 across 5
  distinct individuals).
- Whether T2 actually averages over input parts or candidate
  parts. Current evidence favours input parts but isn't
  conclusive.
- Whether Soundex contributes anything observable. None of
  the 17 queries above produced a hit that was clearly
  driven by phonetic matching rather than character J-W.
  Soundex may be no-op in practice for English-script
  inputs and be dead weight in the algorithm.
- Exact form of edit-distance pre-filter ratio (Levenshtein
  / 2; 1 - normalised-Levenshtein; etc.).

### Empirical run: 10 candidate scorers vs. 171 fixtures

Implemented in `nomenklatura/contrib/ofac2021/compare.py` against
`fixtures.csv` (171 captured rows spanning sliders 50/80/100, Latin
+ Cyrillic, Western and Arabic naming patterns, single-char queries,
common-name explosions, and "did not appear" negatives).

| Scorer | mean \|Δ\| | within ±5 | over +5 | under −5 |
|---|---:|---:|---:|---:|
| `whole_jw` (T1 alone, no gate) | 15.5 | 75 | 6 | 90 |
| `t2_mean` (T2 alone, mean over input parts) | 10.0 | 97 | 14 | 60 |
| `faq249` = max(T1 gated, T2 mean) | 5.5 | 137 | 14 | 20 |
| **`faq249_d2`** = drop input parts ≤2 chars (with single-token protection) | **4.3** | **145** | 14 | 12 |
| `faq249_sx` = T2 with Soundex 1.0-bridge | 6.3 | 126 | 25 | 20 |
| **`faq249_sx85`** = Soundex 0.85 floor | **4.3** | **145** | 14 | 12 |
| **`faq249_meta`** = Metaphone 0.85 floor | **4.3** | **145** | 14 | 12 |
| `faq249_lenr` = T1 × length ratio (moov-io PR-#116 shape) | 7.1 | 116 | 14 | 41 |
| `faq249_pp` = T2 with per-pair first-letter filter | 4.8 | 144 | **7** | 20 |
| `faq249_pp_sx` = pp + Soundex 0.85 floor | 4.8 | 144 | 7 | 20 |

**Three winners on the leaderboard, by metric:**

- **Best mean accuracy**: `faq249_d2` / `faq249_sx85` / `faq249_meta`
  tied at mean \|Δ\| = 4.3, 145/171 within ±5. Soundex/metaphone
  add nothing measurable when the per-pair first-letter check is
  already in place.
- **Best precision profile** (closest to OFAC's conservative
  behavior): `faq249_pp` with only **7 over-predictions** (vs. 14
  for the d2 family).

**Disproved hypotheses:**

- **moov-io's length-ratio penalty (`faq249_lenr`).** Worse than
  the baseline (mean \|Δ\| = 7.1 vs 4.3). OFAC's whole-string
  J-W is *not* multiplied by a length ratio. moov's PR-#116 was
  not the convergence step it appeared to be.
- **Soundex 1.0-bridge (`faq249_sx`).** Too aggressive. PATINO ↔
  PUTIN both P350 → score 100. AL QAIDA → 100. Saturation kills
  precision. A 0.85 floor is the right calibration but it adds
  no value over plain JW once first-letter checks are in place.

**Remaining error patterns** for `faq249_d2` (worst 30 deltas):

- **Long candidates with shared prefix under-score** (`VLADIMIR
  PUTIN ↔ VLADIMIROV, Nikolai Nikolayevich` OFAC 84, model 70).
  Both T1 and T2 are 14 points lower than OFAC. Our whole-string
  J-W is more length-sensitive than OFAC's. Possibly a different
  prefix-bonus cap or a different J-W variant under the hood.
- **`ALQAEDA → AL QAEDA`** OFAC didn't return at slider 80; model
  fires at 97. Some tokenisation rule we haven't recovered —
  joined-form input matching multi-token candidate via T1.
- **Sub-80 cluster around `GEORGE BUSH ↔ HAS{W,A}ANI, George`**
  (OFAC 50, model 73). Per-pair filter (`faq249_pp`) drops these
  to 50 exactly, but breaks `PUTIN VLADIMIR ↔ TURIN, Vladimir`
  (OFAC 92, pp says 50). OFAC's per-part composite appears to
  accept cross-first-letter token pairings when JW is high enough,
  but reject them when JW is low — i.e., the "first-letter check"
  is *implicit* in JW being high enough, not an explicit gate.
- **Fixture-encoding artefact:** "did not appear at slider 80"
  rows encoded as `ofac_score = 0` create spurious +50/+73/+97
  deltas. Refactor to encode threshold semantics properly so we
  measure threshold agreement on these.

**Implementation.** All ten scorers + helpers fit in ~250 lines of
Python over `rapidfuzz` and `rigour.text.phonetics`. The matcher
this produces is small enough to inline into a new `OFACMatcher`
class without further abstraction once we've picked the final
composite shape.

### Parity-fixture canon (initial)

Pin these queries into the regression suite. Each entry is
`(query, slider, expected_top_hits_with_scores)`. Captured
2026-05-01 against SDN list 4/30/2026.

| Query | Slider | Top-3 expected (entity_id, score) |
|---|---:|---|
| VLADIMIR PUTIN | 100 | (35096, 100), (35096, 100) |
| VLADIMIR PUTIN | 80 | (35096, 100), (35096, 100), (—, 90 VLADIMIR BILIY) |
| GEORGE BUSH | 80 | (—, 86 GEORGIOU), (—, 85 GEORGY), (—, 83 GEORGIEVA) |
| GEORGE BUSH | 100 | ∅ |
| BUSH GEORGE | 80 | ∅ |
| Владимир Путин | 80 | ∅ |
| PUTIN | 80 | (35096, 100), (35096, 100), (51142, 97) |
| PUTIN VLADIMIR | 80 | (35096, 100), (35096, 100), (23243, 92 TURIN, Vladimir) |
| VLADIMR PUTIN | 80 | (35096, 99), (35096, 99) |
| VLADIMIR PUTNI | 80 | (35096, 98), (35096, 98) |
| PUTIN VLADIMIROVICH | 80 | (35096, 100), (35096, 97) |
| OSAMA BIN LADEN | 80 | (6365, 100), (6365, 97), (6365, 97) |
| USAMA BIN LADIN | 80 | (6365, 100), (6365, 100), (6365, 97) |
| KIM JONG UN | 80 | (20157, 100), 4 other ind. @ 100 |
| MOHAMMED ALI | 80 | 100+ hits @ 100, common-name explosion |
| JOHN SMITH | 80 | (46882, 85), (46882, 85), (46882, 84) |
| MAHMOOD AHMED BASHIR-UD-DIN | 80 | (45129, 92), (7133, 90), (45129, 90) — wrong-person-on-top case |
| BASHIR-UD-DIN | 80 | (7133, 100), (19930, 91), (20881, 87) — distinctive-part query lands right person |
| BASHIR UD DIN | 80 | (7133, 100), … (hyphen→space equivalence) |
| AL-QAEDA | 80 | (6366, 100), (20159, 100), (13041, 100) |
| AL QAEDA | 80 | same as AL-QAEDA, hyphen→space proof |
| ALQAEDA | 80 | top score 91, no 100s — joined-form is a different token |
| MAHMUD AHMAD BASHIRUDDIN | 80 | top score 90, no 100s — MAHMUD↔MAHMOOD doesn't bridge cleanly |
| ABDUL RAHMAN | 80 | 225 hits top-100, common-name explosion |
| ABDULRAHMAN | 80 | 505 hits top-100, common-name explosion (different population) |

The parity check passes when our emulator's top-N hit set
(by entity ID, not by row) matches OFAC's at each slider
setting, with score-band agreement (±5 points) on the
overlapping hits. **Score exactness is not the bar; set and
band agreement are.**

## Implications for the emulator

1. **Reproduce, don't improve.** Where OFAC's algorithm is
   permissive, ours is permissive. Where it is restrictive
   (the first-letter pre-filter, the implicit length-ratio
   behavior of the composite-across-parts step), ours is
   restrictive. Resist the temptation to apply
   `name-screening.md` lessons here — those are for the
   default matcher, not for this one.
2. **Implement the blocker exactly.** First-letter match on
   the input's first character; 50% edit-distance similarity
   minimum. Both OFAC's documented gates. The blocker is what
   stops "George Bush" from returning Habbash at all — at
   least for full-string comparisons. Per-name-part
   comparisons may not respect first-letter; needs empirical
   check.
3. **Implement both techniques and take the max.** Whole-
   string J-W on one path; per-name-part J-W∪Soundex with a
   composite-across-parts aggregator on the other. Reported
   score is the higher.
4. **The composite-across-parts aggregator is the
   reverse-engineering problem.** FAQ 249 says it produces
   "a composite score for all name parts entered" but does
   not say how. Candidates worth testing against the parity
   fixture: arithmetic mean, length-weighted mean, geometric
   mean, max, Hungarian-assignment best-pairing. Pick the one
   that minimises the parity error on the fixture; document
   the choice.
5. **Score on name only.** Address, type, country, ID, DOB
   filter the candidate set but do not feed the score (FAQ
   251). Mirror this. Filters belong in the candidate-
   generation layer, not the scorer.
6. **Use the public 0–100 scale.** Output integer 0–100 with
   100 = exact, mirroring the slider semantics. Internal
   computation can be float; the output convention is
   public-tool-facing.
7. **Treat alias quality empirically.** Build the parity
   fixture first; check whether OFAC's tool actually demotes
   `LowQuality` aliases in its returned scores. If yes,
   replicate; if no, ignore the flag in the emulator (even
   though doing so is a worse policy outcome).
8. **Soundex on Latin tokens only.** The classic Soundex
   algorithm only works on a-z; non-Latin tokens should bypass
   the phonetic technique. This presumably matches OFAC's
   behavior implicitly because their input pipeline assumes
   Latin script; verify against the parity fixture for
   Cyrillic / Arabic / Chinese inputs.
9. **No transliteration in the matcher.** OFAC's tool does not
   active-transliterate; coverage relies on the SDN list
   carrying transliterated aliases. The emulator should
   match — no normality / rigour transliteration in this
   code path.
10. **Where the emulator differs from logic_v2, document
    why.** Customer support will get "the OFAC emulator says
    X but logic_v2 says Y" tickets. A short side-by-side
    doc — both are intentional, here's why — closes these
    faster than re-litigating per ticket.

## Building the parity fixture

This is the load-bearing artefact. Without it we cannot
measure convergence and the emulator is just a pile of
opinions.

Shape:

- ~50–200 query strings, drawn from realistic patterns:
  common Western names, transliterated Russian / Arabic /
  Chinese names, names with qualifiers, names with typos,
  initials-only inputs, the "George Bush"-style false-
  friend cases.
- For each query, capture from the live OFAC tool, at
  multiple slider settings (50, 70, 80, 90, 100): the
  ranked list of returned hits and their scores.
- Persist in a versioned JSON or YAML file under
  `nomenklatura/contrib/ofac_parity/`.
- Note the SDN list version (date) at capture time, since
  the list changes daily.

Capture mechanism: the OFAC search tool serves results from
a server-side endpoint. Inspect the network tab to find the
endpoint and whether it's stable enough to script. If
stable, a periodic re-capture (quarterly?) keeps the fixture
fresh as OFAC's tool evolves. If not, manual capture of a
small fixed set is acceptable — even 30 queries gives useful
parity signal.

Parity metric:

- **Set agreement** at each threshold: precision and recall
  of returned hit IDs against OFAC's hit IDs. This is the
  primary metric.
- **Rank correlation** (Spearman) on the overlapping hits.
  Score values can drift; ordering is what matters.
- **Score band agreement**: did each hit land in the same
  10-point band as OFAC's? This is the loosest metric and
  the easiest to defend.

We declare "substantial emulation" when set agreement is
≥ 90% at the 80% threshold across the fixture. Earlier
than that, we keep iterating. After that, we accept and
move on.

## Open questions / verification TODO

- [x] FAQs 247, 249, 250 — wording verified against OFAC
  directly (2026-05-01, FL).
- [ ] Re-verify FAQs 5, 82, 122, 123, 124, 246, 248, 251, 252
  directly. Research relied on search-result snippets because
  treasury.gov was rate-limiting WebFetch.
- [ ] Resolve the third-algorithm question. Either FAQ 252
  text or the January 2021 recent-actions notice should
  answer it; the current FAQ 249 (April 2021) does not.
- [ ] Build the initial parity fixture (~30 queries) and
  measure baseline divergence vs. naive J-W and vs. moov-io's
  current state.
- [ ] Empirically determine the composite-across-parts
  aggregator by sweeping mean / weighted-mean / max / etc.
  against the parity fixture.
- [ ] Empirically determine whether OFAC's tool demotes
  `LowQuality` aliases in returned scores. If yes, replicate.
- [ ] Inspect the live tool's HTTP traffic to find a stable
  search endpoint suitable for fixture capture. If none, fall
  back to manual capture of a fixed set.
- [ ] Confirm the SDN_ADVANCED.XML schema element / attribute
  for `LowQuality` (capitalisation, location in the document,
  whether it's on `Alias` or on a child).
- [ ] Audit zavod's OFAC SDN crawler: does it preserve
  `LowQuality` into followthemoney? If yes, on what property?
- [ ] Confirm the May 2024 namespace change has been absorbed
  by zavod's parser — any silent breakage there would mean
  our matcher is operating on stale data.
- [ ] Cross-check moov-io/watchman's current matching code as
  prior art. Their convergence work is parallel; we may save
  effort by adopting (and improving on) their length-ratio
  penalty and blocker logic rather than re-deriving.

## Sources

OFAC tool and FAQs:

- [Sanctions List Search Tool — landing page](https://ofac.treasury.gov/sanctions-list-search-tool)
- [Sanctions List Search — live tool](https://sanctionssearch.ofac.treas.gov/)
- [FAQ topic 1636 — How to Search OFAC's Sanctions Lists](https://ofac.treasury.gov/faqs/topic/1636)
- [FAQ topic 1591 — Assessing OFAC Name Matches](https://ofac.treasury.gov/faqs/topic/1591)
- [FAQ topic 1646 — Weak Aliases](https://ofac.treasury.gov/faqs/topic/1646)
- [FAQ topic 1521 — 50 Percent Rule](https://ofac.treasury.gov/faqs/topic/1521)
- [FAQ 5 — How do I determine if I have a valid OFAC match?](https://ofac.treasury.gov/faqs/5)
- [FAQ 82 — Web-based search tool](https://ofac.treasury.gov/faqs/82)
- [FAQ 122 — Weak aliases](https://ofac.treasury.gov/faqs/122)
- [FAQ 123 — Where to find weak aliases](https://ofac.treasury.gov/faqs/123)
- [FAQ 124 — Required to screen for weak aliases?](https://ofac.treasury.gov/faqs/124)
- [FAQ 246 — How does Sanctions List Search work?](https://ofac.treasury.gov/faqs/246)
- [FAQ 247 — What does the Score mean?](https://ofac.treasury.gov/faqs/247)
- [FAQ 248 — Minimum Name Score / slider](https://ofac.treasury.gov/faqs/248)
- [FAQ 249 — How is the Score calculated?](https://ofac.treasury.gov/faqs/249)
- [FAQ 250 — Threshold recommendation](https://ofac.treasury.gov/faqs/250)
- [FAQ 251 — Only the name field influences the score](https://ofac.treasury.gov/faqs/251)
- [FAQ 252 — Differences vs. previous version (Jan 25, 2021)](https://ofac.treasury.gov/faqs/252)
- [Recent Action — Sanctions List Search Upgrade, 25 Jan 2021](https://ofac.treasury.gov/recent-actions/20210125)
- [Recent Action — Clarification on SDN alias screening, 21 Jan 2011](https://ofac.treasury.gov/recent-actions/20110121)

Data formats:

- [SDN List Data Formats & Schemas](https://ofac.treasury.gov/specially-designated-nationals-list-data-formats-data-schemas)
- [SDN List Data Specification (PDF)](https://ofac.treasury.gov/media/29976/download?inline=)
- [Advanced Sanctions List Standard FAQ](https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/frequently-asked-questions-on-advanced-sanctions-list-standard)
- [Namespace change in SDN.XML / SDN_ADVANCED.XML, May 2024](https://ofac.treasury.gov/recent-actions/20240507_44)
- [Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service)

Compliance posture / 50% rule:

- [Framework for OFAC Compliance Commitments, May 2019 (PDF)](https://ofac.treasury.gov/media/16331/download?inline=)
- [Revised 50 Percent Rule guidance, August 2014 (PDF)](https://ofac.treasury.gov/media/6186/download?inline=)

Open-source prior art:

- [moov-io/watchman issue #115 — Results inconsistent with Treasury.gov](https://github.com/moov-io/watchman/issues/115)
- [moov-io/watchman PR #116 — limit string similarity to length ratio](https://github.com/moov-io/watchman/pull/116)
- [jbillay/kyc-agent issue #19 — generic fuzzy matcher user story](https://github.com/jbillay/kyc-agent/issues/19)
- [lapc506/compliance-core issue #19 — MatchNormalizer task stub](https://github.com/lapc506/compliance-core/issues/19)

Comparable regulators:

- [UK FCDO Sanctions List Search](https://search-uk-sanctions-list.service.gov.uk/)
- [UK Sanctions List Search Tool — User Guide](https://www.gov.uk/government/publications/the-uk-sanctions-list/uk-sanctions-list-search-tool-user-guide)
- [Moving to a single UK list, 28 Jan 2026](https://www.gov.uk/guidance/moving-to-a-single-list-for-uk-sanctions-designations-28-january-2026)
- [EU Consolidated Financial Sanctions list (data.europa.eu)](https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions?locale=en)
- [EU Sanctions Map](https://www.sanctionsmap.eu/)
