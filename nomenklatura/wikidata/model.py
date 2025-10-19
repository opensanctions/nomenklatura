from normality import stringify
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from nomenklatura.wikidata.value import snak_value_to_string
from nomenklatura.wikidata.lang import LangText

if TYPE_CHECKING:
    from nomenklatura.wikidata.client import WikidataClient


class Snak(object):
    """Some Notation About Knowledge (TM)."""

    def __init__(self, client: "WikidataClient", data: Dict[str, Any]):
        self.client = client
        datavalue = data.pop("datavalue", {})
        self.value_type: str = datavalue.pop("type", None)
        self._value = datavalue.pop("value", None)
        data.pop("hash", None)
        self.type = data.pop("datatype", None)
        self.property: Optional[str] = data.pop("property", None)
        self.snaktype = data.pop("snaktype", None)
        # self._data = data

    @property
    def property_label(self) -> LangText:
        return self.client.get_label(self.property)

    @property
    def qid(self) -> Optional[str]:
        if self.value_type == "wikibase-entityid":
            return stringify(self._value.get("id"))
        return None

    @property
    def text(self) -> LangText:
        return snak_value_to_string(self.client, self.value_type, self._value)

    def __repr__(self) -> str:
        return f"<Snak({self.qid}, {self.property}, {self.value_type})>"


class Reference(object):
    def __init__(self, client: "WikidataClient", data: Dict[str, Any]) -> None:
        self.snaks: Dict[str, List[Snak]] = {}
        for prop, snak_data in data.pop("snaks", {}).items():
            self.snaks[prop] = [Snak(client, s) for s in snak_data]

    def get(self, prop: str) -> List[Snak]:
        return self.snaks.get(prop, [])


class Claim(Snak):
    def __init__(
        self, client: "WikidataClient", data: Dict[str, Any], prop: str
    ) -> None:
        self.id = data.pop("id")
        self.rank = data.pop("rank")
        super().__init__(client, data.pop("mainsnak"))
        self.qualifiers: Dict[str, List[Snak]] = {}
        for prop, snaks in data.pop("qualifiers", {}).items():
            self.qualifiers[prop] = [Snak(client, s) for s in snaks]

        self.references = [Reference(client, r) for r in data.pop("references", [])]
        self.property = self.property or prop

    def get_qualifier(self, prop: str) -> List[Snak]:
        return self.qualifiers.get(prop, [])

    @property
    def is_ended(self) -> bool:
        snak = self.qualifiers.get("P582")
        if snak is not None and len(snak) > 0:
            return True
        return False

    def __repr__(self) -> str:
        return f"<Claim({self.qid}, {self.property}, {self.value_type})>"

    def __hash__(self) -> int:
        return hash((self.qid, self.property, self.id))


class Item(object):
    """A wikidata item (or entity)."""

    def __init__(self, client: "WikidataClient", data: Dict[str, Any]) -> None:
        self.client = client
        self.id: str = data.pop("id")
        self.modified: Optional[str] = data.pop("modified", None)

        self.labels: Set[LangText] = LangText.from_dict(data.pop("labels", {}))
        self.aliases: Set[LangText] = LangText.from_dict(data.pop("aliases", {}))

        descriptions = LangText.from_dict(data.pop("descriptions", {}))
        self.description = LangText.pick(descriptions)

        self.claims: List[Claim] = []
        claims: Dict[str, List[Dict[str, Any]]] = data.pop("claims", {})
        for prop, values in claims.items():
            for value in values:
                self.claims.append(Claim(client, value, prop))

        # TODO: get back to this later:
        data.pop("sitelinks", None)

    @property
    def label(self) -> Optional[LangText]:
        label = LangText.pick(self.labels)
        if label is not None:
            return label
        return LangText.pick(self.aliases)

    @property
    def sorted_labels(self) -> List[LangText]:
        return LangText.sorted(self.labels)

    @property
    def sorted_aliases(self) -> List[LangText]:
        return LangText.sorted(self.aliases)

    def is_instance(self, qid: str) -> bool:
        for claim in self.claims:
            if claim.property == "P31" and claim.qid == qid:
                return True
        return False

    def _types(self, path: List[str]) -> Set[str]:
        qid = path[-1]
        types = set([qid])
        if len(path) > 6:
            return types
        for type_ in self.client._type_props(qid):
            if type_ not in path:
                types.update(self._types(path + [type_]))
        return types

    @property
    def types(self) -> Set[str]:
        """Get all the `instance of` and `subclass of` types for an item."""
        return self._types([self.id])

    def __repr__(self) -> str:
        return f"<Item({self.id})>"

    def __hash__(self) -> int:
        return hash(self.id)
