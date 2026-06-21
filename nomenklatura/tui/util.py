from typing import Generator, Tuple
from followthemoney import DS, registry, Property, SE

from nomenklatura.db import Session
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.store import Store

TYPE_ORDER = {
    registry.name: -6,
    registry.identifier: -5,
    registry.date: -4,
    registry.country: -3,
    registry.string: -1,
    registry.text: 3,
    registry.url: 5,
}

# Properties shown even though they're non-matchable instances of a matchable
# type. The filter below hides those by default (to drop noise like alephUrl),
# but a Wikipedia link is exactly the kind of context a reviewer wants.
ALWAYS_SHOW = {"wikipediaUrl"}


def apply_judgement(
    session: Session,
    resolver: Resolver[SE],
    store: Store[DS, SE],
    left_id: str,
    right_id: str,
    judgement: Judgement,
) -> str:
    """Record a judgement between two entity ids and reflect it in the store.

    The `decide → store.update → checkpoint` triad is easy to get wrong (the
    store must be re-keyed to the new canonical id, and the order matters), so
    both the dedupe and reconcile UIs route through here. Returns the canonical
    id the two entities now share.
    """
    canonical = resolver.decide(left_id, right_id, judgement=judgement)
    store.update(canonical.id)
    session.checkpoint()
    return canonical.id


def comparison_props(left: SE, right: SE) -> Generator[Property, None, None]:
    """Return an ordered list of properties to be shown in a comparison of
    the two given entities."""
    props = set(left.iterprops())
    props.update(right.iterprops())
    weights = {p.name: TYPE_ORDER.get(p.type, 0) for p in props}
    for prop in props:
        for schema in (left.schema, right.schema):
            if prop.name in schema.featured:
                weights[prop.name] -= 10

    def sort_props(prop: Property) -> Tuple[int, str]:
        return (weights[prop.name], prop.label)

    for prop in sorted(props, key=sort_props):
        if prop.hidden:
            continue
        if prop.name not in ALWAYS_SHOW and prop.type.matchable and not prop.matchable:
            continue
        # if prop.type == registry.entity:
        #     continue
        yield prop
