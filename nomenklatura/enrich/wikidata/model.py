from normality import stringify
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from nomenklatura.enrich.wikidata.value import snak_value_to_string
from nomenklatura.enrich.wikidata.lang import pick_obj_lang

if TYPE_CHECKING:
    from nomenklatura.enrich.wikidata import WikidataEnricher


class Snak(object):
    """Some Notation About Knowledge (TM)."""

    def __init__(self, data: Dict[str, Any]):
        datavalue = data.pop("datavalue", {})
        self.value_type: str = datavalue.pop("type", None)
        self._value = datavalue.pop("value", None)
        data.pop("hash", None)
        self.type = data.pop("datatype", None)
        self.property: Optional[str] = data.pop("property", None)
        self.snaktype = data.pop("snaktype", None)
        # self._data = data

    def property_label(self, enricher: "WikidataEnricher") -> Optional[str]:
        return enricher.get_label(self.property)

    @property
    def qid(self) -> Optional[str]:
        if self.value_type == "wikibase-entityid":
            return stringify(self._value.get("id"))
        return None

    def text(self, enricher: "WikidataEnricher") -> Optional[str]:
        return snak_value_to_string(enricher, self.value_type, self._value)


class Reference(object):
    def __init__(self, data: Dict[str, Any]) -> None:
        self.snaks: Dict[str, List[Snak]] = {}
        for prop, snak_data in data.pop("snaks", {}).items():
            self.snaks[prop] = [Snak(s) for s in snak_data]

    def get(self, prop: str) -> List[Snak]:
        return self.snaks.get(prop, [])


class Claim(Snak):
    def __init__(self, data: Dict[str, Any], prop: str) -> None:
        self.id = data.pop("id")
        self.rank = data.pop("rank")
        super().__init__(data.pop("mainsnak"))
        self.qualifiers: Dict[str, List[Snak]] = {}
        for prop, snaks in data.pop("qualifiers", {}).items():
            self.qualifiers[prop] = [Snak(s) for s in snaks]

        self.references = [Reference(r) for r in data.pop("references", [])]
        self.property = self.property or prop

    def get_qualifier(self, prop: str) -> List[Snak]:
        return self.qualifiers.get(prop, [])


class Item(object):
    """A wikidata item (or entity)."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data.pop("id")
        self.modified: Optional[str] = data.pop("modified", None)

        labels: Dict[str, Dict[str, str]] = data.pop("labels", {})
        self.label = pick_obj_lang(labels)
        self.aliases: Set[str] = set()
        for obj in labels.values():
            self.aliases.add(obj["value"])

        aliases: Dict[str, List[Dict[str, str]]] = data.pop("aliases", {})
        for lang in aliases.values():
            for obj in lang:
                self.aliases.add(obj["value"])

        if self.label is not None:
            self.aliases.discard(self.label)

        descriptions: Dict[str, Dict[str, str]] = data.pop("descriptions", {})
        self.description = pick_obj_lang(descriptions)

        self.claims: List[Claim] = []
        claims: Dict[str, List[Dict[str, Any]]] = data.pop("claims", {})
        for prop, values in claims.items():
            for value in values:
                self.claims.append(Claim(value, prop))

        # TODO: get back to this later:
        data.pop("sitelinks", None)

    def is_instance(self, qid: str) -> bool:
        for claim in self.claims:
            if claim.property == "P31" and claim.qid == qid:
                return True
        return False
