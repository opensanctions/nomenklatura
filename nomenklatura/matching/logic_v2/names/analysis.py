from functools import lru_cache
from typing import Optional, Set, Tuple
from rigour.names import Name
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
