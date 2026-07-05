# Enrichers

An enricher connects entities to an external data source, implementing a match step that finds candidate records and an expand step that fetches related entities.

For the workflow these classes plug into — configuration files, the `nk match` and `nk enrich` commands, and the role of the resolver — see the [enrichment guide](../enrichment.md). This page documents the framework interface and the configuration options of each built-in enricher.

All enrichers accept the shared options `cache_days`, `schemata`, and `topics`, described in the [enrichment guide](../enrichment.md#configuring-an-enricher). String options can reference environment variables with `${VAR}` syntax.

## Framework

::: nomenklatura.enrich.make_enricher

::: nomenklatura.enrich.match

::: nomenklatura.enrich.enrich

::: nomenklatura.enrich.Enricher

::: nomenklatura.enrich.EnrichmentException

::: nomenklatura.enrich.EnrichmentAbort

## Wikidata

::: nomenklatura.enrich.wikidata.WikidataEnricher
    options:
        members: false

- `depth` — how many hops of family and associate relationships to follow from a matched person (default 1).
- `aliases` — also search on the entity's alias names, not only its primary names (default false).
- `search_limit` — how many search results to consider per name (default 7).

The enricher builds on the [Wikidata client](wikidata.md).

## yente

::: nomenklatura.enrich.yente.YenteEnricher
    options:
        members: false

- `api` (required) — base URL of the yente instance, e.g. `https://api.opensanctions.org/`.
- `dataset` — the yente dataset scope to match against (default `default`).
- `api_key` — API key, sent as an `Authorization` header. Falls back to the `YENTE_API_KEY` environment variable.
- `algorithm` — the yente scoring algorithm to use (default `best`).
- `cutoff` — minimum score for returned candidates.
- `fuzzy` — enable fuzzy name matching in the query (default false).
- `expand_nested` — include related entities when expanding a match (default true).
- `strip_namespace` — remove [namespace](https://followthemoney.tech/docs/namespace/) suffixes from entity IDs (default false).

## Aleph

::: nomenklatura.enrich.aleph.AlephEnricher
    options:
        members: false

- `host` — base URL of the Aleph instance. Falls back to the `ALEPH_HOST` environment variable, then `https://aleph.occrp.org/`.
- `api_key` — Aleph API key. Falls back to the `ALEPH_API_KEY` environment variable.
- `collection` — foreign ID of a collection to search within; if unset, the whole instance is searched.
- `strip_namespace` — remove namespace suffixes from entity IDs (default false).

## OpenCorporates

::: nomenklatura.enrich.opencorporates.OpenCorporatesEnricher
    options:
        members: false

- `api_token` — OpenCorporates API token. Defaults to the `OPENCORPORATES_API_TOKEN` environment variable.
- `skip_jurisdictions` — list of jurisdiction codes to exclude from lookups.

## OpenFIGI

::: nomenklatura.enrich.openfigi.OpenFIGIEnricher
    options:
        members: false

- `api_key` — OpenFIGI API key. Defaults to the `OPENFIGI_API_KEY` environment variable.

## PermID

::: nomenklatura.enrich.permid.PermIDEnricher
    options:
        members: false

- `api_token` — PermID API token. Defaults to the `PERMID_API_TOKEN` environment variable.

## BrightQuery

::: nomenklatura.enrich.brightquery.BrightQueryEnricher
    options:
        members: false

- `api_key` (required) — BrightQuery API key. Defaults to the `BRIGHTQUERY_API_KEY` environment variable.
- `skip_jurisdictions` — list of jurisdiction codes to exclude, for entities outside BrightQuery's US coverage.
