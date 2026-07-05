Enrichers connect entities to external data sources. They implement the
`nomenklatura.enrich.Enricher` abstract class: a `match()` step that yields
candidate entities from the source, and an `expand()` step that yields a
confirmed match together with its related entities.

Full documentation, including the configuration options of each built-in
enricher and the surrounding workflow, lives on the docs site:

- [Enrichment guide](../../docs/enrichment.md)
- [Enricher reference](../../docs/reference/enrich.md)
