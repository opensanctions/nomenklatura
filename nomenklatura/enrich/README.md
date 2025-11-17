Enrichers implement the `nomenklatura.enrich.Enricher` abstract class.

## Subject entities

They can be configured to apply only to specific entities via their configuration dictionary:

- `schemata` - list of FTM schemata - entity must match one
- `topics` - list of FTM topics - entity must match one

All criteria must be satisfied.

## Implementation

Every enricher should implement

- `match(self, entity: SE) -> Generator[SE, None, None]`
- `expand(self, entity: SE, match: SE) -> Generator[SE, None, None]`


### Match

The match step is called to discover potential matches in the enrichment source.
It is called for all entities in the configured input datasets, matching the
configured constraints on e.g. schema and topics.

It should yield any potential matches found in the enrichment source.


### Expand

The expand step is called to discover entities related to a matched entity in the enrichment source.
It is called for any candidates that have been deemed a true match.

At a minimum, the match should be yielded. Additionally, related entities found
in the enrichment source should be yielded.
