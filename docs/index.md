# nomenklatura

`nomenklatura` is a data integration and enrichment framework for
[followthemoney](https://followthemoney.tech) data. It de-duplicates and links
records that describe the same real-world entity, and enriches them against
external sources.

## Capabilities

* **Entity resolution** — record the human and automated judgements that decide
  whether two entities are the same, and apply them consistently across a dataset.
* **Matching** — score candidate pairs of entities using configurable matching
  algorithms.
* **Cross-referencing (`xref`)** — find likely duplicate candidates within and
  across datasets at scale.
* **Enrichment** — look up entities against external data sources (e.g. Wikidata,
  OpenCorporates) and merge in the results.
* **Stores** — read and write followthemoney entities and statements to a range
  of storage backends.

## Related resources

This library is part of a broader ecosystem of tools:

* [FollowTheMoney](https://followthemoney.tech) — the data model `nomenklatura` operates on
* [rigour](https://rigour.followthemoney.tech/) — text cleaning and validation used throughout
* [yente](https://yente.followthemoney.tech/) — matching API server built on this library
* OpenSanctions: [open source projects](https://www.opensanctions.org/docs/opensource/)
