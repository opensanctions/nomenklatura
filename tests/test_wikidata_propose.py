import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.cache import Cache
from nomenklatura.wikidata import WikidataClient
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.propose import propose_create, propose_enrich
from nomenklatura.wikidata.write import (
    AddStatement,
    CreateItem,
    SetAlias,
    SetLabel,
    serialize,
)

from .conftest import wd_read_response

DATASET = Dataset.make({"name": "wikidata", "title": "Wikidata"})


def _person():
    """A reasonably populated OS person to diff against Wikidata."""
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-putin"})
    entity.add("name", "Vladimir Putin")  # untagged -> mul
    entity.add("name", "Владимир Путин", lang="rus")  # -> ru
    entity.add("alias", "Vova")
    entity.add("birthDate", "1952-10-07")
    entity.add("gender", "male")
    entity.add("citizenship", "ru")
    entity.add("citizenship", "suhh")  # USSR: historical, must be excluded
    entity.add("sourceUrl", "https://example.org/putin")
    return entity


def _statement(commands, prop):
    for command in commands:
        if isinstance(command, AddStatement) and command.prop == prop:
            return command
    return None


def _empty_item():
    """A bare item with no claims, labels or aliases — everything is 'missing'."""
    return Item(None, {"id": "Q999", "labels": {}, "aliases": {}, "claims": {}})


def test_propose_create_full():
    commands = propose_create(_person(), retrieved="2026-06-14")
    assert isinstance(commands[0], CreateItem)

    labels = [c for c in commands if isinstance(c, SetLabel)]
    aliases = [c for c in commands if isinstance(c, SetAlias)]
    # Exactly one label (the primary name); the rest are aliases.
    assert len(labels) == 1
    assert labels[0].text in ("Vladimir Putin", "Владимир Путин")
    alias_texts = {a.text for a in aliases}
    assert "Vova" in alias_texts

    # FtM 3-letter langs map to Wikidata codes; untagged names become `mul`.
    langs = {c.text: c.lang for c in labels + aliases}
    assert langs["Vladimir Putin"] == "mul"
    assert langs["Владимир Путин"] == "ru"

    # P31 human, birth date with day precision, male gender:
    assert _statement(commands, "P31").value.render() == "Q5"
    assert _statement(commands, "P569").value.render() == "+1952-10-07T00:00:00Z/11"
    assert _statement(commands, "P21").value.render() == "Q6581097"

    # Citizenship: present-day Russia (Q159) only; USSR (Q15180) is dropped.
    p27 = [
        c for c in commands if isinstance(c, AddStatement) and c.prop == "P27"
    ]
    assert {c.value.render() for c in p27} == {"Q159"}

    # Every statement is sourced: S854 url + S813 retrieved date.
    refs = _statement(commands, "P31").references
    assert refs[0][0] == "S854"
    assert refs[0][1].render() == '"https://example.org/putin"'
    assert refs[1][0] == "S813"


def test_propose_enrich_empty_item():
    # An item that knows nothing gets the same facts as a create, but names land
    # as aliases (never labels — QS would overwrite) and target the QID.
    commands = propose_enrich(_person(), _empty_item())
    assert not any(isinstance(c, (CreateItem, SetLabel)) for c in commands)
    assert all(
        c.target == "Q999"
        for c in commands
        if isinstance(c, (SetAlias, AddStatement))
    )
    alias_texts = {c.text for c in commands if isinstance(c, SetAlias)}
    assert "Vladimir Putin" in alias_texts
    assert _statement(commands, "P31") is not None
    assert _statement(commands, "P569") is not None
    assert {c.value.render() for c in commands if isinstance(c, AddStatement) and c.prop == "P27"} == {"Q159"}


def test_propose_enrich_diffs_against_item(test_cache: Cache):
    # Real Putin already has P31/P569/P21/P27 and his names: enrich emits nothing.
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=wd_read_response)
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q7747")
    assert item is not None
    commands = propose_enrich(_person(), item)
    assert _statement(commands, "P31") is None
    assert _statement(commands, "P569") is None
    assert _statement(commands, "P21") is None


def test_propose_skips_other_gender():
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-x"})
    entity.add("name", "Sam Doe")
    entity.add("gender", "other")
    commands = propose_enrich(entity, _empty_item())
    assert _statement(commands, "P21") is None


def test_propose_skips_conflicting_birthdate():
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-x"})
    entity.add("name", "Sam Doe")
    entity.add("birthDate", ["1950-01-01", "1951-02-02"])
    commands = propose_enrich(entity, _empty_item())
    assert _statement(commands, "P569") is None


def test_propose_unsourced_still_emits(caplog):
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-x"})
    entity.add("name", "Sam Doe")
    entity.add("birthDate", "1950-01-01")
    commands = propose_enrich(entity, _empty_item())
    p569 = _statement(commands, "P569")
    assert p569 is not None
    # Best-effort sourcing: no sourceUrl -> no references, but a statement still.
    assert p569.references == []
    assert "No sourceUrl" in caplog.text


def test_propose_source_url_fallback():
    # An entity without its own sourceUrl uses the passed fallback (e.g. dataset
    # URL under zavod).
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-x"})
    entity.add("name", "Sam Doe")
    entity.add("birthDate", "1950-01-01")
    commands = propose_enrich(entity, _empty_item(), source_url="https://os.org/ds")
    p569 = _statement(commands, "P569")
    assert p569 is not None
    assert p569.references[0][0] == "S854"
    assert p569.references[0][1].render() == '"https://os.org/ds"'


def test_propose_source_url_prefers_entity():
    # The entity's own sourceUrl wins over the fallback.
    entity = Entity.from_data(DATASET, {"schema": "Person", "id": "os-x"})
    entity.add("name", "Sam Doe")
    entity.add("birthDate", "1950-01-01")
    entity.add("sourceUrl", "https://entity.example/own")
    commands = propose_enrich(entity, _empty_item(), source_url="https://os.org/ds")
    p569 = _statement(commands, "P569")
    assert p569 is not None
    assert p569.references[0][1].render() == '"https://entity.example/own"'


def test_serialize_create_roundtrip():
    # The composed batch renders to valid tab-separated V1 lines.
    commands = propose_create(_person(), retrieved="2026-06-14")
    text = serialize(commands)
    lines = text.split("\n")
    assert lines[0] == "CREATE"
    assert any(line.startswith("LAST\tP31\tQ5") for line in lines)
    assert "\tP27\tQ159\t" in text
    assert "Q15180" not in text  # USSR never emitted
