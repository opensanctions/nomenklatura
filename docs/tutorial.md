# Tutorial: deduplicating a multi-source dataset

Combine data about German politicians from several publishers into one dataset, then find and merge the duplicate entities using the `nk` command line.

Different sources describe the same real-world people and organizations, each with its own identifiers and naming quirks. This tutorial walks the full `nomenklatura` workflow on real data: convert source entities into statements, cross-reference them to find likely duplicates, judge candidate pairs in an interactive terminal interface, and produce a merged dataset in which each person is one entity — with every source claim still traceable.

The pipeline has a loop at its heart:

```text
download → statements → combine → resolve → aggregate
                            ↑                   ↓
                            └── dedupe ← xref ──┘
```

The first pass through `resolve` does nothing, because no deduplication decisions exist yet. After `xref` and `dedupe` have produced decisions, running the pipeline again folds them into the output.

## Prerequisites

- A Python environment with `nomenklatura` installed (`pip install nomenklatura`). This provides the `nk` command, and — through the [FollowTheMoney (FtM)](https://followthemoney.tech/) dependency — the `ftm` command.
- [`qsv`](https://github.com/dathere/qsv) for fast CSV operations.
- `curl` for downloads.

## The source data

The tutorial uses three datasets. All are published as FtM entities, one JSON object per line, so there is nothing to scrape or map:

- **`de_abgeordnetenwatch_full`** — members of German parliaments, their mandates, and parties, collected by [abgeordnetenwatch.de](https://www.abgeordnetenwatch.de/) and published on [data.ftm.store](https://data.ftm.store/).
- **`de_bundestag`** — the [OpenSanctions](https://www.opensanctions.org/) list of politically exposed persons (PEPs) in the German Bundestag.
- **`az_laundromat`** — people and companies from the Azerbaijani Laundromat, a money-laundering and influence scheme that reached European politicians.

The same member of parliament appears in the first two datasets — under differently formatted names and with different identifiers. Whether anyone appears in the third one is the investigative question that deduplication answers.

Create a working directory and download the data (about 55 MB in total):

```bash
mkdir -p data/src data/stmt
curl -sf -o data/src/de_abgeordnetenwatch_full.json \
    https://data.ftm.store/de_abgeordnetenwatch_full/entities.ftm.json
curl -sf -o data/src/de_bundestag.json \
    https://data.opensanctions.org/datasets/latest/de_bundestag/entities.ftm.json
curl -sf -o data/src/az_laundromat.json \
    https://data.opensanctions.org/datasets/latest/az_laundromat/entities.ftm.json
```

## Step 1: break entities into statements

A [statement](https://followthemoney.tech/docs/statements/) is one atomic claim: "entity X has property `name` with value Y, according to dataset Z". Decomposing entities into statements is what makes the rest of the workflow possible — statements from many sources can be pooled, re-grouped under a shared ID when entities are merged, and each value keeps its provenance throughout.

Convert each file, tagging its statements with the dataset name:

```bash
for ds in de_abgeordnetenwatch_full de_bundestag az_laundromat; do
    ftm statements -d $ds -f csv data/src/$ds.json -o data/stmt/$ds.csv
done
```

## Step 2: combine the sources into one table

Concatenate the statement tables. Long free-text values (`prop_type` of `text`, such as descriptions) don't help with matching, so filter them out:

```bash
qsv cat rows data/stmt/*.csv \
    | qsv search -v -s prop_type '^text$' -o data/combined.csv
```

## Step 3: apply the resolver

The [resolver](reference/resolver.md) is the database of deduplication decisions. `nk apply-statements` streams statements through it and sets each statement's `canonical_id` — the identifier of the merged entity it belongs to:

```bash
nk apply-statements -f csv -i data/combined.csv -o data/resolved.csv
```

This command creates a SQLite database named `nomenklatura.db` in the working directory. On this first run it holds no decisions, so every statement keeps its original entity ID as its canonical ID. The step will matter on the second pass.

## Step 4: aggregate statements into entities

Statements that share a canonical ID collapse into one entity. The aggregation command expects its input sorted by canonical ID:

```bash
qsv sort -s canonical_id data/resolved.csv \
    | ftm aggregate-statements -f csv -i - -o data/entities.json
```

The result, `data/entities.json`, is a stream of FtM entities combining all three sources — with duplicates still unmerged.

## Step 5: find duplicate candidates with xref

`nk xref` builds a [blocking index](reference/blocker.md) over the entities, so only pairs that share tokens — name parts, phonetic forms, identifiers — are considered. Each candidate pair is then scored by a [matching algorithm](reference/matching.md); the default for `xref` is `er-unstable`, a regression model trained for deduplication.

```bash
nk xref -a 0.96 data/entities.json
```

Pairs scoring at or above the `-a` threshold are merged automatically. The rest are stored in the resolver as suggestions, ranked by score, awaiting a human decision. Useful options:

- `-l <NUMBER>` — how many candidate pairs to keep (default 5000).
- `-f <DATASET>` — only suggest pairs where one entity comes from the given dataset. `-f az_laundromat` concentrates review effort on the laundromat connections.
- `--algorithm <NAME>` — choose a different scoring algorithm.

The blocking index is written to `nomenklatura.data/` and reused on later runs.

## Step 6: judge the candidates

Open the interactive deduplication interface:

```bash
nk dedupe data/entities.json
```

The screen shows one candidate pair at a time, property by property. Decide with a single keypress:

- ++x++ — the two entities are the same (match)
- ++n++ — they are different (no match)
- ++u++ — unsure, skip for now
- ++q++ — quit

Each decision is written to the resolver immediately. You don't have to finish the queue — judge the high-scoring pairs and quit whenever you want to see results.

## Step 7: run the merge again

Repeat steps 3 and 4 to fold the decisions into the output:

```bash
nk apply-statements -f csv -i data/combined.csv -o data/resolved.csv
qsv sort -s canonical_id data/resolved.csv \
    | ftm aggregate-statements -f csv -i - -o data/entities.json
```

Merged politicians are now single entities carrying claims from AbgeordnetenWatch and OpenSanctions side by side — one node per person, with each property value still attributable to its source. The `xref` → `dedupe` → merge cycle can be repeated as often as needed; each round starts from the decisions already made.

## Keeping, sharing, and resetting decisions

Judgements are the product of careful human work — treat them like source code. Export them to a plain-text file that can live in version control:

```bash
nk dump-resolver judgements.ijson
```

To restore them into a fresh database (or a colleague's), run `nk load-resolver judgements.ijson`.

Two cleanup commands are useful during iteration. `nk prune` deletes undecided suggestions from the resolver — run it before a fresh `xref` to clear out stale candidates. To start over completely, delete `nomenklatura.db` and the `nomenklatura.data/` directory.

**Note:** the resolver defaults to SQLite, which suits a single-person project. If you set the `NOMENKLATURA_DB_URL` environment variable to a PostgreSQL database, several people can judge candidates against the same resolver.

## Where to go next

- Add more datasets to the pipeline — any source of FtM entities plugs into step 1. [data.ftm.store](https://data.ftm.store/) and [OpenSanctions](https://www.opensanctions.org/datasets/) publish many, including the German federal lobby register (`de_lobbyregister`) and the EU transparency register (`eu_transparency_register`).
- Match your entities against external databases with `nk match` and `nk enrich`, which query sources like Wikidata, OpenCorporates, or a [yente](https://yente.followthemoney.tech/) instance.
- Load the merged dataset into Neo4j with [followthemoney-graph](https://github.com/opensanctions/followthemoney-graph) to explore it as a network.
