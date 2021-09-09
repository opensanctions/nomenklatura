from pathlib import Path
from tempfile import NamedTemporaryFile
from followthemoney.dedupe.judgement import Judgement
from nomenklatura.graph import Graph, Identifier


def test_graph():
    graph = Graph()
    graph.decide("a1", "a2", Judgement.POSITIVE)
    assert Identifier.get("a2") in graph.connected(Identifier.get("a1"))
    assert graph.get_judgement("a1", "a2") == Judgement.POSITIVE
    graph.decide("b1", "b2", Judgement.POSITIVE)
    assert graph.get_judgement("a1", "b1") == Judgement.NO_JUDGEMENT
    graph.decide("a2", "b2", Judgement.NEGATIVE)
    assert graph.get_judgement("a2", "b2") == Judgement.NEGATIVE
    assert graph.get_judgement("a1", "b1") == Judgement.NEGATIVE
    graph.suggest("a1", "b1", 7.0)
    assert graph.get_judgement("a1", "b1") == Judgement.NEGATIVE

    assert graph.get_canonical("a1") == "a1"
    assert graph.get_canonical("a2") == "a2"

    graph.suggest("c1", "c2", 7.0)
    assert graph.get_edge("c1", "c2").score == 7.0
    graph.suggest("c1", "c2", 8.0)
    assert graph.get_edge("c1", "c2").score == 8.0
    graph.decide("c1", "c2", Judgement.POSITIVE)
    assert graph.get_edge("c1", "c2").score is None


def test_graph_store():
    graph = Graph()
    graph.decide("a1", "a2", Judgement.POSITIVE)
    graph.decide("a2", "b2", Judgement.NEGATIVE)
    graph.suggest("a1", "c1", 7.0)

    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        graph.save(path)

        other = Graph.load(path)
        assert len(other.edges) == len(graph.edges)
        assert graph.get_edge("a1", "c1").score == 7.0


def test_graph_candidates():
    graph = Graph()
    graph.decide("a1", "a2", Judgement.POSITIVE)
    graph.decide("a2", "b2", Judgement.NEGATIVE)
    graph.suggest("a1", "b2", 7.0)
    graph.suggest("a1", "c1", 5.0)
    graph.suggest("a1", "d1", 4.0)

    candidates = list(graph.get_candidates())
    assert len(candidates) == 2, candidates
    assert candidates[0][2] == 5.0, candidates
