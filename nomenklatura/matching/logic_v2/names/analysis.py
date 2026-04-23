from functools import lru_cache
from typing import Dict, FrozenSet, Iterator, List, Optional, Set, Tuple
from rigour.names import Name, Symbol
from rigour.text.scripts import common_scripts
from followthemoney import EntityProxy
from followthemoney.names import entity_names as ftm_entity_name

from nomenklatura.matching.util import MEMO_BATCH


# NOTE: This @lru_cache uses Entity.__hash__, which only compares IDs. So if the properties of
# the underlying entity change, this cache will not be invalidated.
@lru_cache(maxsize=MEMO_BATCH)
def entity_names(
    entity: EntityProxy,
    prop: Optional[str] = None,
    is_query: bool = False,
) -> Set[Name]:
    """This will transform the entity into a set of names with tags applied. The idea
    is to tag the names with the type of entity they are, e.g. person, organization,
    etc. and to tag the parts of the name with their type, e.g. first name, last name,
    etc.
    """
    # nb. Putting an @lru_cache here does not make sense for an individual use of the matcher,
    # but will cache the name objects for the `query` entity across multiple possible `results`.
    # It also requires for the `entity` to have an ID so that hashing it does not raise an
    # exception.
    props: Optional[Tuple[str, ...]] = None
    if prop is not None:
        props = (prop,)
    return ftm_entity_name(entity, props, infer_initials=is_query, consolidate=False)


def names_product(
    queries: Set[Name],
    results: Set[Name],
) -> Iterator[Tuple[Name, Name]]:
    """Enumerate (query, result) name pairs worth feeding into the scoring core.

    Prunes the cross product of two Name sets with two rules:

    - **Script-sharing pairs pass unconditionally.** If the two names share
      any real Unicode script (per `rigour.text.scripts.common_scripts` on
      the `comparable` forms), the pair is kept.
    - **Symbol-overlap rescue with per-query dominance.** For pairs that do
      not share any real script, keep only those with a non-empty symbol
      overlap; and within each query, drop pairs whose symbol overlap is a
      strict subset of another kept pair's overlap. Weaker symbolic
      evidence is subsumed by stronger evidence for the same query — the
      scoring core would score the dominator at least as highly as the
      dominated, so running both is wasted work.

    Empty-script inputs (numeric-only, punctuation-only) naturally fall
    through to the symbol-overlap rescue — they never match the script
    gate, but they also aren't special-cased. A name like "007" survives
    against "Agent 007" via shared NUMERIC symbols.
    """
    if len(queries) * len(results) <= 6:
        # For small products, skip the pruning and just yield everything.
        for q in queries:
            for r in results:
                yield (q, r)
        return

    # Materialise symbols once per Name; the getter is not cached.
    q_syms: List[Tuple[Name, FrozenSet[Symbol]]] = [
        (q, frozenset(q.symbols)) for q in queries
    ]
    r_syms: List[Tuple[Name, FrozenSet[Symbol]]] = [
        (r, frozenset(r.symbols)) for r in results
    ]

    # First pass: script-sharing pairs always keep; no-script-overlap
    # pairs with symbol overlap are bucketed per query for the dominance
    # check in the second pass.
    script_ok: List[Tuple[Name, Name]] = []
    per_query_symbol: Dict[Name, List[Tuple[Name, FrozenSet[Symbol]]]] = {}
    for q, qs in q_syms:
        for r, rs in r_syms:
            if common_scripts(q.comparable, r.comparable):
                script_ok.append((q, r))
                continue
            overlap = qs & rs
            if overlap:
                per_query_symbol.setdefault(q, []).append((r, overlap))

    # Script-ok pairs survive unconditionally.
    yield from script_ok

    # Symbol-only pairs: drop those whose overlap is a strict subset of
    # another pair's overlap for the same query. Equal overlaps all
    # survive (no strict-subset relationship).
    for q, cands in per_query_symbol.items():
        overlaps = [o for _, o in cands]
        for r, overlap in cands:
            if any(overlap < other for other in overlaps):
                continue  # strictly dominated — skip
            yield (q, r)
