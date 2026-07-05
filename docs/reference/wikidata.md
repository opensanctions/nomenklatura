# Wikidata

`WikidataClient` reads items from the Wikidata API and SPARQL endpoint, with language-aware label selection and database-backed caching of responses.

[Wikidata](https://www.wikidata.org/) is a useful source of structured data on politicians, companies, and other entities of interest. This module is the low-level client used by the [Wikidata enricher](enrich.md#wikidata) and by crawlers that turn Wikidata items into FollowTheMoney entities. It handles the parts that are error-prone to reimplement: request throttling and retries, response caching via a `nomenklatura.cache.Cache`, and picking a display label from the many languages an item may carry.

The client returns items as [Item][nomenklatura.wikidata.Item] objects, which expose labels, aliases, descriptions, and claims. A [Claim][nomenklatura.wikidata.Claim] is one property statement on an item — for example `P569` (date of birth) — with its qualifiers and references. Text values are wrapped in [LangText][nomenklatura.wikidata.LangText], which keeps the language tag alongside the string.

Fetching an item requires a `Cache`, which stores API responses in the same SQL database the rest of `nomenklatura` uses:

```python
from followthemoney import Dataset
from nomenklatura.cache import Cache
from nomenklatura.db import make_session
from nomenklatura.wikidata import WikidataClient

dataset = Dataset.make({"name": "wikidata_demo", "title": "Wikidata demo"})
with make_session() as session:
    cache = Cache(session, dataset, create=True)
    client = WikidataClient(cache)
    item = client.fetch_item("Q7747")
    if item is not None:
        print(item.id, client.get_label(item.id))
```

## Interface

::: nomenklatura.wikidata.WikidataClient

::: nomenklatura.wikidata.Item

::: nomenklatura.wikidata.Claim

::: nomenklatura.wikidata.LangText
