from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.resolver import Resolver
from nomenklatura.store import load_entity_file_store
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.propose import PositionClaim, propose_enrich
from nomenklatura.wikidata.reconcile import position_claims
from nomenklatura.wikidata.write import AddStatement


def _claim(prop: str, qid: str) -> dict:
    """A minimal wbgetentities claim asserting an item-valued property."""
    return {
        "id": f"{prop}-{qid}",
        "rank": "normal",
        "mainsnak": {
            "property": prop,
            "snaktype": "value",
            "datatype": "wikibase-item",
            "datavalue": {"type": "wikibase-entityid", "value": {"id": qid}},
        },
    }


def _item(*position_qids: str) -> Item:
    claims = {"P39": [_claim("P39", qid) for qid in position_qids]} if position_qids else {}
    return Item(None, {"id": "Q1", "claims": claims})  # type: ignore[arg-type]


def _p39(cmds):
    return [c for c in cmds if isinstance(c, AddStatement) and c.prop == "P39"]


def test_propose_enrich_positions():
    ds = Dataset.make({"name": "x"})
    person = Entity.from_data(
        ds,
        {
            "schema": "Person",
            "id": "p1",
            "properties": {"name": ["Jane Doe"], "sourceUrl": ["https://example.org"]},
        },
    )
    item = _item("Q100")  # the item already holds Q100
    positions = [
        PositionClaim("Q100", start="2010", end="2015"),  # held already -> skipped
        PositionClaim("Q200", start="2019-01-02", end="2024-05-30"),  # single -> dated
        PositionClaim("Q300", start="2010", end="2015"),  # two occupancies ->
        PositionClaim("Q300", start="2019", end="2024"),  #   bare, no span
    ]
    p39 = _p39(propose_enrich(person, item, positions=positions))
    assert {c.value.qid for c in p39} == {"Q200", "Q300"}

    q200 = next(c for c in p39 if c.value.qid == "Q200")
    assert [q[0] for q in q200.qualifiers] == ["P580", "P582"]

    # Re-election: a QID seen through several occupancies stays bare.
    q300 = next(c for c in p39 if c.value.qid == "Q300")
    assert q300.qualifiers == []


def test_propose_enrich_no_positions():
    ds = Dataset.make({"name": "x"})
    person = Entity.from_data(
        ds, {"schema": "Person", "id": "p1", "properties": {"name": ["Jane Doe"]}}
    )
    assert _p39(propose_enrich(person, _item())) == []


def _store(tmp_path, resolver, *lines: str):
    path = tmp_path / "e.ijson"
    path.write_text("\n".join(lines) + "\n")
    return load_entity_file_store(path, resolver=resolver)


def test_position_claims_dates_and_qid(tmp_path, resolver: Resolver[Entity]):
    resolver.begin()
    store = _store(
        tmp_path,
        resolver,
        '{"id":"Q900","schema":"Position","properties":{"name":["MP"]}}',
        '{"id":"occ1","schema":"Occupancy","properties":'
        '{"holder":["p1"],"post":["Q900"],'
        '"startDate":["2019-01-02"],"endDate":["2024-05-30"]}}',
        '{"id":"p1","schema":"Person","properties":{"name":["Jane Doe"]}}',
    )
    view = store.default_view()
    person = view.get_entity("p1")
    assert person is not None
    claims = position_claims(view, person)
    assert claims == [PositionClaim("Q900", "2019-01-02", "2024-05-30")]


def test_position_claims_period_fallback_and_skips_unqid(
    tmp_path, resolver: Resolver[Entity]
):
    resolver.begin()
    store = _store(
        tmp_path,
        resolver,
        # QID position, only the term dates -> P580/P582 fall back to period*.
        '{"id":"Q900","schema":"Position","properties":{"name":["MP"]}}',
        '{"id":"occ1","schema":"Occupancy","properties":'
        '{"holder":["p1"],"post":["Q900"],'
        '"periodStart":["2019"],"periodEnd":["2024"]}}',
        # Non-QID position -> skipped, never looked up.
        '{"id":"pos-x","schema":"Position","properties":{"name":["Dogcatcher"]}}',
        '{"id":"occ2","schema":"Occupancy","properties":'
        '{"holder":["p1"],"post":["pos-x"]}}',
        '{"id":"p1","schema":"Person","properties":{"name":["Jane Doe"]}}',
    )
    view = store.default_view()
    person = view.get_entity("p1")
    assert person is not None
    assert position_claims(view, person) == [PositionClaim("Q900", "2019", "2024")]
