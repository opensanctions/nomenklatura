from functools import lru_cache
from typing import Set
from followthemoney import EntityProxy, registry, E
from followthemoney.names import schema_type_tag
from rigour.text.distance import levenshtein_similarity
from rigour.names import Name, NameTypeTag
from rigour.names import is_stopword
from rigour.names import remove_org_prefixes, remove_obj_prefixes
from rigour.names import remove_person_prefixes
from rigour.names import replace_org_types_compare

from nomenklatura.matching.erun.util import compare_levenshtein
from nomenklatura.matching.util import max_in_sets, has_schema
from nomenklatura.util import unroll


@lru_cache(maxsize=512)
def _entity_names(entity: EntityProxy) -> Set[Name]:
    names: Set[Name] = set()
    tag = schema_type_tag(entity.schema)
    for string in entity.get_type_values(registry.name, matchable=True):
        if tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            string = replace_org_types_compare(string)
            string = remove_org_prefixes(string)
        elif tag == NameTypeTag.PER:
            string = remove_person_prefixes(string)
        else:
            string = remove_obj_prefixes(string)
        n = Name(string, tag=tag)
        names.add(n)
    return names


def name_levenshtein(left: E, right: E) -> float:
    """Consider the edit distance (as a fraction of name length) between the two most
    similar names linked to both entities."""
    if not has_schema(left, right, "LegalEntity"):
        return 0.0
    if has_schema(left, right, "Person"):
        left_names: Set[str] = set()
        for name in _entity_names(left):
            left_names.add(" ".join(sorted(part.comparable for part in name.parts)))
            left_names.add(name.comparable)
        right_names: Set[str] = set()
        for name in _entity_names(right):
            right_names.add(" ".join(sorted(part.comparable for part in name.parts)))
            right_names.add(name.comparable)
    else:
        left_names = {n.comparable for n in _entity_names(left)}
        right_names = {n.comparable for n in _entity_names(right)}
    return max_in_sets(left_names, right_names, compare_levenshtein)


def _entity_lastnames(entity: EntityProxy) -> Set[str]:
    names: Set[str] = set()
    for string in entity.get("lastName", quiet=True):
        n = Name(string, tag=NameTypeTag.PER)
        for part in n.parts:
            if len(part.comparable) > 2 and not is_stopword(part.form):
                names.add(part.comparable)
    return names


def family_name_match(left: E, right: E) -> float:
    """Matching family name between the two entities."""
    if not has_schema(left, right, "Person"):
        return 0.0
    lnames = _entity_lastnames(left)
    rnames = _entity_lastnames(right)
    if len(lnames) == 0 or len(rnames) == 0:
        return 0.0
    overlap = lnames.intersection(rnames)
    return -1.0 if len(overlap) == 0 else 1.0


def _name_tokens(entity: EntityProxy) -> Set[str]:
    tokens: Set[str] = set()
    for name in _entity_names(entity):
        for part in name.parts:
            cmp = part.comparable
            if len(cmp) > 2 and not is_stopword(part.form):
                tokens.add(cmp)
    return tokens


def name_token_overlap(left: E, right: E) -> float:
    """Evaluate the proportion of identical words in each name."""
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    common = left_tokens.intersection(right_tokens)
    tokens = min(len(left_tokens), len(right_tokens))
    return float(len(common)) / float(max(2.0, tokens))


def name_numbers(left: E, right: E) -> float:
    """Find if names contain numbers, score if the numbers are different."""
    left_names = [n.parts for n in _entity_names(left)]
    right_names = [n.parts for n in _entity_names(right)]
    left_numbers = {p.comparable for p in unroll(left_names) if p.numeric}
    right_numbers = {p.comparable for p in unroll(right_names) if p.numeric}
    total = len(left_numbers) + len(right_numbers)
    if total == 0:
        return 0.0
    common = len(left_numbers.intersection(right_numbers))
    if common == 0 and len(left_numbers) > 0 and len(right_numbers) > 0:
        # If both names contain numbers, but they are different, this is a strong
        # signal that the names are not the same.
        return -1.0
    return common / float(total)


def _compare_strict_levenshtein(left: str, right: str) -> float:
    """A stricter version of levenshtein that returns 0.0 if the names are too
    different in length."""
    max_edits = min(2, max(len(left), len(right)) // 4)
    score = levenshtein_similarity(left, right, max_edits=max_edits)
    return score**2


def obj_name_levenshtein(left: E, right: E) -> float:
    """Very strict name comparison on object (Vessel, RealEstate, Security) names."""
    if has_schema(left, right, "LegalEntity", "Security", "RealEstate", "CryptoWallet"):
        return 0.0
    left_names = {n.comparable for n in _entity_names(left)}
    right_names = {n.comparable for n in _entity_names(right)}
    return max_in_sets(left_names, right_names, _compare_strict_levenshtein)
