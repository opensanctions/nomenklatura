# nomenklatura

Nomenklatura de-duplicates and integrates different [Follow the Money](https://followthemoney.rtfd.org/) entities. It serves to clean up messy data and to find links between different datasets.

## Design

This package will offer an implementation of an in-memory data deduplication framework centered around the FtM data model. The idea is the following workflow:

* Accept FtM-shaped entities from a given loader (e.g. a JSON file, or a database)
* Build an in-memory inverted index of the entities for blocking
* Generate merge candidates using the blocking index and FtM compare
* Provide a file-based storage format for merge challenges and decisions
* Provide a text-based user interface to let users make merge decisions

Later on, the following might be added:

* A web application to let users make merge decisions on the web
* An implementation of the OpenRefine Reconciliation API based on the blocking index

This will be done in typed Python 3.

## Reading

* https://dedupe.readthedocs.org/en/latest/
* https://github.com/OpenRefine/OpenRefine/wiki/Reconcilable-Data-Sources
* https://github.com/OpenRefine/OpenRefine/wiki/Clustering-In-Depth
* https://github.com/OpenRefine/OpenRefine/wiki/Reconciliation-Service-API


## Contact, contributions etc.

This codebase is licensed under the terms of an MIT license (see LICENSE).

We're keen for any contributions, bug fixes and feature suggestions, please use the GitHub issue tracker for this repository. 

Nomenklatura is currently developed thanks to a Prototypefund grant for [OpenSanctions](https://opensanctions.org). Previous iterations of the package were developed with support from [Knight-Mozilla OpenNews](http://opennews.org) and the [Open Knowledge Foundation Labs](http://okfnlabs.org).
