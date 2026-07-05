# Enrichment

Enrichment looks up your entities in external databases — Wikidata, corporate registries, a [yente](https://yente.followthemoney.tech/) instance — and merges confirmed matches and their related records into your dataset.

A dataset rarely tells the whole story on its own. The people in it have Wikidata items listing their family members; the companies have registry records naming their officers. Enrichment connects an entity stream to such a source, with the [resolver](reference/resolver.md) acting as the quality gate: nothing is merged until a match has been confirmed, either by a human or by a score threshold you control.

The workflow has three steps, each of which can be run repeatedly:

1. **Match** — query the external source for each entity and record candidate matches as suggestions in the resolver.
2. **Judge** — confirm or reject the suggestions, e.g. in the `nk dedupe` interface.
3. **Enrich** — for confirmed matches, fetch the external record and its related entities.

## Configuring an enricher

An enricher is configured in a YAML file. The file doubles as [dataset metadata](https://followthemoney.tech/docs/metadata/) — the entities an enricher produces are tagged with its `name`, so their origin stays visible after merging. A configuration for matching against the US OFAC sanctions list, served by the OpenSanctions API:

```yaml
name: us_ofac_sdn
title: US OFAC Specially Designated Nationals
type: nomenklatura.enrich.yente:YenteEnricher
api: https://api.opensanctions.org/
dataset: us_ofac_sdn
api_key: ${YENTE_API_KEY}
cache_days: 30
```

The `type` key selects the enricher implementation by import path. The remaining keys depend on the enricher — see the [enricher reference](reference/enrich.md) for each implementation's options. Three options work for every enricher:

- `cache_days` — how long fetched API responses stay valid in the local cache (default 90). Responses are cached in the same SQL database that holds the resolver, so re-runs don't hit the remote API again.
- `schemata` — a list of schema names; only entities of one of these schemata are looked up.
- `topics` — a list of [topics](https://followthemoney.tech/explorer/types/topic/); only entities carrying one of them are looked up. Use this to enrich, say, only entities tagged `role.pep`.

Values in the configuration can reference environment variables with `${VAR}` syntax — keep API keys out of the file itself.

## Step 1: find candidate matches

`nk match` streams an entity file through the enricher. The output contains each input entity followed by the candidates found for it, and every candidate pair is recorded in the resolver as a scored suggestion:

```bash
nk match us_ofac_sdn.yml entities.json -o candidates.json
```

## Step 2: judge the candidates

The suggestions land in the same review queue that `nk xref` feeds. Judge them in the interactive interface, using the output file from the match step so both sides of each pair are on screen:

```bash
nk dedupe candidates.json
```

Press ++x++ to confirm a match, ++n++ to reject it. Only confirmed pairs are enriched.

## Step 3: fetch the enrichment data

`nk enrich` runs the same lookup, but now only acts on pairs the resolver holds a positive judgement for. For each confirmed match, it fetches the external record and the entities related to it — officers of a matched company, family members of a matched person:

```bash
nk enrich us_ofac_sdn.yml entities.json -o enriched.json
```

The output is a stream of new entities from the external source, not a modified copy of your input. Combine it with your source data the same way any dataset gets merged — through the statements pipeline described in the [deduplication tutorial](tutorial.md). Because the matched external record shares a canonical ID with your entity, aggregation folds them into one.

## Available enrichers

| Name | Source | Matches |
| --- | --- | --- |
| `WikidataEnricher` | [Wikidata](https://www.wikidata.org/) | People |
| `YenteEnricher` | A [yente](https://yente.followthemoney.tech/) instance | All matchable schemata |
| `AlephEnricher` | An [Aleph / OpenAleph](https://openaleph.org/docs/) instance | All matchable schemata |
| `OpenCorporatesEnricher` | [OpenCorporates](https://opencorporates.com/) | Companies, officers |
| `OpenFIGIEnricher` | [OpenFIGI](https://www.openfigi.com/) | Organizations, securities |
| `PermIDEnricher` | [PermID](https://permid.org/) (LSEG) | Organizations |
| `BrightQueryEnricher` | [BrightQuery](https://brightquery.com/) (US companies) | Organizations |

Configuration options for each are documented in the [enricher reference](reference/enrich.md), which also describes the `Enricher` interface to implement for connecting a new source.
