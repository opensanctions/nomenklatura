import os
import pytest
from nomenklatura.versions import Version, VersionHistory


def test_version():
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


def test_run_history():
    original = VersionHistory([])
    assert original.latest is None
    assert original.to_json() == '{"items": []}'

    runid = Version.new()
    history = original.append(runid)
    assert len(history) == 1
    assert len(original) == 0
    assert history.latest == runid
    assert history.to_json() == f'{{"items": ["{runid.id}"]}}'

    runid2 = Version.new()
    history = history.append(runid2)
    assert history.latest == runid2
    assert history.to_json() == f'{{"items": ["{runid.id}", "{runid2.id}"]}}'
    assert len(list(history)) == 2

    other = VersionHistory.from_json(history.to_json())
    assert other.latest == runid2

    for _ in range(10000):
        history = history.append(Version.new())
        assert len(history) <= VersionHistory.LENGTH

    history = VersionHistory([runid, runid2])
    assert history.latest == runid2
    assert history.to_json() == f'{{"items": ["{runid.id}", "{runid2.id}"]}}'
