import os
import pytest
from typing import Optional
from nomenklatura.versions import Version, VersionHistory


def test_version() -> None:
    runid = Version.new("aaa")
    assert runid.id.startswith(runid.dt.strftime("%Y%m%d%H%M%S"))
    assert len(runid.tag) == 3
    assert len(runid.id) == 18
    assert str(runid) == runid.id
    assert repr(runid) == f"Version({runid.id})"
    runid2 = Version.new("bbb")
    assert runid2.id != runid.id
    assert hash(runid2) == hash(runid2.id)

    with pytest.raises(ValueError):
        Version.from_string("foo")

    os.environ["NK_RUN_ID"] = runid.id
    runid3 = Version.from_env("NK_RUN_ID")
    assert runid3.id == runid.id

    runid4 = Version.from_env("NK_RUN2222_ID")
    assert runid4.id != runid2.id

    prev_id: Optional[Version] = None
    for i in range(100):
        next_id = Version.new()
        if prev_id is not None:
            assert next_id.dt >= prev_id.dt, (next_id, prev_id)
        prev_id = next_id


def test_run_history():
    original = VersionHistory([])
    assert original.latest is None
    assert original.to_json() == '{"items": [], "last_successful": null}'

    runid = Version.new()
    history = original.append(runid)
    assert len(history) == 1
    assert len(original) == 0
    assert history.latest == runid
    assert history.last_successful is None
    assert history.to_json() == f'{{"items": ["{runid.id}"], "last_successful": null}}'

    history.last_successful = runid
    assert history.to_json() == f'{{"items": ["{runid.id}"], "last_successful": "{runid.id}"}}'
    assert history.last_successful == runid

    runid2 = Version.new()
    history = history.append(runid2)
    assert history.latest == runid2
    assert history.to_json() == f'{{"items": ["{runid.id}", "{runid2.id}"], "last_successful": "{runid.id}"}}'
    assert len(list(history)) == 2
    # check that the last_successful is not updated automatically
    assert history.last_successful == runid

    # test that the load-store cycle works
    other = VersionHistory.from_json(history.to_json())
    assert other.latest == runid2
    assert other.last_successful == runid

    for _ in range(10000):
        history = history.append(Version.new())
        assert len(history) <= VersionHistory.LENGTH

    history = VersionHistory([runid, runid2])
    assert history.latest == runid2
    assert history.to_json() == f'{{"items": ["{runid.id}", "{runid2.id}"], "last_successful": null}}'
