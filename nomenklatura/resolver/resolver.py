import getpass
from pathlib import Path
from datetime import datetime
from functools import lru_cache
from collections import defaultdict
from typing import Dict, Generator, List, Optional, Set, Tuple
from rigour.ids.wikidata import is_qid

from nomenklatura.entity import CE
from nomenklatura.judgement import Judgement
from nomenklatura.resolver.identifier import Identifier, StrIdent, Pair
from nomenklatura.resolver.edge import Edge
from nomenklatura.resolver.linker import Linker
from nomenklatura.util import PathLike


class Resolver(Linker[CE]):
    UNDECIDED = (Judgement.NO_JUDGEMENT, Judgement.UNSURE)

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.edges: Dict[Pair, Edge] = {}
        self.nodes: Dict[Identifier, Set[Edge]] = defaultdict(set)

    def get_linker(self) -> Linker[CE]:
        """Return a linker object that can be used to resolve entities.
        This is less memory-consuming than the full resolver object.
        """
        entities: Dict[Identifier, Set[Identifier]] = {}
        for node in self.nodes.keys():
            if node in entities:
                continue
            connected = self._traverse(node, set())
            for c in connected:
                entities[c] = connected
        return Linker(entities)

    def get_edge(self, left_id: StrIdent, right_id: StrIdent) -> Optional[Edge]:
        key = Identifier.pair(left_id, right_id)
        return self.edges.get(key)

    def _traverse(self, node: Identifier, seen: Set[Identifier]) -> Set[Identifier]:
        connected = set([node])
        if node in seen:
            return connected
        seen.add(node)
        for edge in self.nodes.get(node, []):
            if edge.judgement == Judgement.POSITIVE:
                other = edge.other(node)
                rec = self._traverse(other, seen)
                connected.update(rec)
        return connected

    @lru_cache(maxsize=200000)
    def connected(self, node: Identifier) -> Set[Identifier]:
        return self._traverse(node, set())

    def canonicals(self) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        for node in self.nodes.keys():
            if not node.canonical:
                continue
            canonical = self.get_canonical(node)
            if canonical == node.id:
                yield node

    def get_resolved_edge(
        self, left_id: StrIdent, right_id: StrIdent
    ) -> Optional[Edge]:
        (left, right) = Identifier.pair(left_id, right_id)
        left_connected = self.connected(left)
        right_connected = self.connected(right)
        for e in left_connected:
            for o in right_connected:
                edge = self.edges.get(Identifier.pair(e, o))
                if edge is None:
                    continue
                return edge
        return None

    def _pair_judgement(self, left: Identifier, right: Identifier) -> Judgement:
        edge = self.edges.get(Identifier.pair(left, right))
        if edge is not None:
            return edge.judgement
        return Judgement.NO_JUDGEMENT

    def get_judgement(self, entity_id: StrIdent, other_id: StrIdent) -> Judgement:
        """Get the existing decision between two entities with dedupe factored in."""
        entity = Identifier.get(entity_id)
        other = Identifier.get(other_id)
        if entity == other:
            return Judgement.POSITIVE
        entity_connected = self.connected(entity)
        if other in entity_connected:
            return Judgement.POSITIVE

        # HACK: this would mark pairs only as unsure if the unsure judgement
        # had been made on the current canonical combination:
        # canon_edge = self._pair_judgement(max(entity_connected), max(other_connected))
        # if canon_edge == Judgement.UNSURE:
        #     return Judgement.UNSURE

        other_connected = self.connected(other)
        for e in entity_connected:
            for o in other_connected:
                judgement = self._pair_judgement(e, o)
                if judgement != Judgement.NO_JUDGEMENT:
                    return judgement

        if is_qid(entity.id) and is_qid(other.id):
            return Judgement.NEGATIVE
        return Judgement.NO_JUDGEMENT

    def check_candidate(self, left: StrIdent, right: StrIdent) -> bool:
        """Check if the two IDs could be merged, i.e. if there's no existing
        judgement."""
        judgement = self.get_judgement(left, right)
        return judgement == Judgement.NO_JUDGEMENT

    def _get_suggested(self) -> List[Edge]:
        """Get all NO_JUDGEMENT edges in descending order of score."""
        edges_all = self.edges.values()
        candidates = (e for e in edges_all if e.judgement == Judgement.NO_JUDGEMENT)
        cmp = lambda x: x.score or -1.0  # noqa
        return sorted(candidates, key=cmp, reverse=True)

    def get_candidates(
        self, limit: Optional[int] = None
    ) -> Generator[Tuple[str, str, Optional[float]], None, None]:
        returned = 0
        for edge in self._get_suggested():
            if not self.check_candidate(edge.source, edge.target):
                continue
            yield edge.target.id, edge.source.id, edge.score
            returned += 1
            if limit is not None and returned >= limit:
                break

    def suggest(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        score: float,
        user: Optional[str] = None,
    ) -> Identifier:
        """Make a NO_JUDGEMENT link between two identifiers to suggest that a user
        should make a decision about whether they are the same or not."""
        edge = self.get_edge(left_id, right_id)
        if edge is not None:
            if edge.judgement == Judgement.NO_JUDGEMENT:
                edge.score = score
            return edge.target
        return self.decide(
            left_id, right_id, Judgement.NO_JUDGEMENT, score=score, user=user
        )

    def decide(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        judgement: Judgement,
        user: Optional[str] = None,
        score: Optional[float] = None,
    ) -> Identifier:
        edge = self.get_edge(left_id, right_id)
        if edge is None:
            edge = Edge(left_id, right_id, judgement=judgement)

        # Canonicalise positive matches, i.e. make both identifiers refer to a
        # canonical identifier, instead of making a direct link.
        if judgement == Judgement.POSITIVE:
            connected = set(self.connected(edge.target))
            connected.update(self.connected(edge.source))
            target = max(connected)
            if not target.canonical:
                canonical = Identifier.make()
                self._remove_edge(edge)
                self.decide(edge.source, canonical, judgement=judgement, user=user)
                self.decide(edge.target, canonical, judgement=judgement, user=user)
                return canonical

        edge.judgement = judgement
        edge.timestamp = datetime.utcnow().isoformat()[:16]
        edge.user = user or getpass.getuser()
        edge.score = score or edge.score
        self._register(edge)
        self.connected.cache_clear()
        return edge.target

    def _register(self, edge: Edge) -> None:
        if edge.judgement != Judgement.NO_JUDGEMENT:
            edge.score = None
        self.edges[edge.key] = edge
        self.nodes[edge.source].add(edge)
        self.nodes[edge.target].add(edge)

    def _remove_edge(self, edge: Edge) -> None:
        """Remove an edge from the graph."""
        self.edges.pop(edge.key, None)
        for node in (edge.source, edge.target):
            if node in self.nodes:
                self.nodes[node].discard(edge)

    def _remove_node(self, node: Identifier) -> None:
        """Remove a node from the graph."""
        edges = self.nodes.get(node)
        if edges is None:
            return
        for edge in list(edges):
            if edge.judgement != Judgement.NO_JUDGEMENT:
                self._remove_edge(edge)

    def remove(self, node_id: StrIdent) -> None:
        """Remove all edges linking to the given node from the graph."""
        node = Identifier.get(node_id)
        self._remove_node(node)
        self.connected.cache_clear()

    def explode(self, node_id: StrIdent) -> Set[str]:
        """Dissolve all edges linked to the cluster to which the node belongs.
        This is the hard way to make sure we re-do context once we realise
        there's been a mistake."""
        node = Identifier.get(node_id)
        affected: Set[str] = set()
        for part in self.connected(node):
            affected.add(str(part))
            self._remove_node(part)
        self.connected.cache_clear()
        return affected

    def prune(self) -> None:
        """Remove suggested (i.e. NO_JUDGEMENT) edges, keep only the n with the
        highest score. This also checks if a transitive judgement has been
        established in the mean time and removes those candidates."""
        for edge in list(self.edges.values()):
            if edge.judgement == Judgement.NO_JUDGEMENT:
                self._remove_edge(edge)
        self.connected.cache_clear()

    def save(self) -> None:
        """Store the resolver adjacency list to a plain text JSON list."""
        if self.path is None:
            raise RuntimeError("Resolver has no path")
        edges = sorted(self.edges.values())
        with open(self.path, "w") as fh:
            for edge in edges:
                fh.write(edge.to_line())

    def merge(self, path: PathLike) -> None:
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                edge = Edge.from_line(line)
                self.decide(
                    edge.source,
                    edge.target,
                    judgement=edge.judgement,
                    user=edge.user,
                    score=edge.score,
                )

    @classmethod
    def load(cls, path: Path) -> "Resolver[CE]":
        resolver = cls(path=path)
        if not path.exists():
            return resolver
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                edge = Edge.from_line(line)
                resolver._register(edge)
        return resolver

    def __repr__(self) -> str:
        path = self.path.name if self.path is not None else ":memory:"
        return f"<Resolver({path!r}, {len(self.edges)})>"
