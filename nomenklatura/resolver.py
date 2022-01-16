import json
import getpass
import shortuuid  # type: ignore
from datetime import datetime
from functools import lru_cache
from collections import defaultdict
from typing import Any, Dict, Generator, Generic, List, Optional, Set, Tuple, Union
from followthemoney.types import registry
from followthemoney.dedupe import Judgement

from nomenklatura.entity import E
from nomenklatura.util import PathLike, is_qid

StrIdent = Union[str, "Identifier"]
Pair = Tuple["Identifier", "Identifier"]


class ResolverLogicError(Exception):
    pass


class Identifier(object):
    PREFIX = "NK-"

    __slots__ = ("id", "canonical", "weight")

    def __init__(self, id: str):
        self.id = id
        self.weight: int = 1
        if self.id.startswith(self.PREFIX):
            self.weight = 2
        elif is_qid(id):
            self.weight = 3
        self.canonical = self.weight > 1

    def __eq__(self, other: Any) -> bool:
        return str(self) == str(other)

    def __lt__(self, other: Any) -> bool:
        return (self.weight, self.id) < (other.weight, other.id)

    def __str__(self) -> str:
        return self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __len__(self) -> int:
        return len(self.id)

    def __repr__(self) -> str:
        return f"<I({self.id})>"

    @classmethod
    def get(cls, id: StrIdent) -> "Identifier":
        if isinstance(id, str):
            return cls(id)
        return id

    @classmethod
    def pair(cls, left_id: StrIdent, right_id: StrIdent) -> Pair:
        left = cls.get(left_id)
        right = cls.get(right_id)
        if left == right:
            raise ResolverLogicError()
        return (max(left, right), min(left, right))

    @classmethod
    def make(cls, value: Optional[str] = None) -> "Identifier":
        key = value or shortuuid.uuid()
        return cls.get(f"{cls.PREFIX}{key}")


class Edge(object):

    __slots__ = ("key", "source", "target", "judgement", "score", "user", "timestamp")

    def __init__(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        judgement: Judgement = Judgement.NO_JUDGEMENT,
        score: Optional[float] = None,
        user: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.key = Identifier.pair(left_id, right_id)
        self.target, self.source = self.key
        self.judgement = judgement
        self.score = score
        self.user = user
        self.timestamp = timestamp

    def other(self, cur: Identifier) -> Identifier:
        if cur == self.target:
            return self.source
        return self.target

    def to_line(self) -> str:
        row = [
            self.target.id,
            self.source.id,
            self.judgement.value,
            self.score,
            self.user,
            self.timestamp,
        ]
        return json.dumps(row) + "\n"

    def __str__(self) -> str:
        return self.to_line()

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __lt__(self, other: Any) -> bool:
        return bool(self.key < other.key)

    def __repr__(self) -> str:
        return f"<E({self.target.id}, {self.source.id}, {self.judgement.value})>"

    @classmethod
    def from_line(cls, line: str) -> "Edge":
        data = json.loads(line)
        return cls(
            data[0],
            data[1],
            judgement=Judgement(data[2]),
            score=data[3],
            user=data[4],
            timestamp=data[5],
        )


class Resolver(Generic[E]):
    UNDECIDED = (Judgement.NO_JUDGEMENT, Judgement.UNSURE)

    def __init__(self, path: Optional[PathLike] = None) -> None:
        self.path = path
        self.edges: Dict[Pair, Edge] = {}
        self.nodes: Dict[Identifier, Set[Edge]] = defaultdict(set)

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

    @lru_cache(maxsize=None)
    def connected(self, node: Identifier) -> Set[Identifier]:
        return self._traverse(node, set())

    def get_canonical(self, entity_id: StrIdent) -> str:
        """Return the canonical identifier for the given entity ID."""
        node = Identifier.get(entity_id)
        best = max(self.connected(node))
        if best.canonical:
            return best.id
        return node.id

    def canonicals(self) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        for node in self.nodes.keys():
            if not node.canonical:
                continue
            canonical = self.get_canonical(node)
            if canonical == node.id:
                yield node

    def get_referents(
        self, canonical_id: StrIdent, canonicals: bool = True
    ) -> Set[str]:
        """Get all the non-canonical entity identifiers which refer to a given
        canonical identifier."""
        node = Identifier.get(canonical_id)
        referents: Set[str] = set()
        for connected in self.connected(node):
            if not canonicals and connected.canonical:
                continue
            if connected == node:
                continue
            referents.add(connected.id)
        return referents

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

    def get_judgement(self, entity_id: StrIdent, other_id: StrIdent) -> Judgement:
        """Get the existing decision between two entities with dedupe factored in."""
        entity = Identifier.get(entity_id)
        other = Identifier.get(other_id)
        entity_connected = self.connected(entity)
        if other in entity_connected:
            return Judgement.POSITIVE
        other_connected = self.connected(other)
        for e in entity_connected:
            for o in other_connected:
                edge = self.edges.get(Identifier.pair(e, o))
                if edge is None:
                    continue
                if edge.judgement == Judgement.NEGATIVE:
                    return edge.judgement
        return Judgement.NO_JUDGEMENT

    def check_candidate(self, left: Identifier, right: Identifier) -> bool:
        """Check if the two IDs could be merged, i.e. if there's no existing
        judgement."""
        judgement = self.get_judgement(left, right)
        return judgement == Judgement.NO_JUDGEMENT

    def _get_suggested(self) -> List[Edge]:
        """Get all NO_JUDGEMENT edges in descending order of score."""
        edges_all = self.edges.values()
        candidates = (e for e in edges_all if e.judgement == Judgement.NO_JUDGEMENT)
        cmp = lambda x: x.score or -1.0
        return sorted(candidates, key=cmp, reverse=True)

    def get_candidates(
        self, limit: int = 100
    ) -> Generator[Tuple[str, str, Optional[float]], None, None]:
        returned = 0
        for edge in self._get_suggested():
            if not self.check_candidate(edge.source, edge.target):
                continue
            yield edge.target.id, edge.source.id, edge.score
            returned += 1
            if returned >= limit:
                break

    def suggest(
        self, left_id: StrIdent, right_id: StrIdent, score: float
    ) -> Identifier:
        """Make a NO_JUDGEMENT link between two identifiers to suggest that a user
        should make a decision about whether they are the same or not."""
        edge = self.get_edge(left_id, right_id)
        if edge is not None:
            if edge.judgement in self.UNDECIDED:
                edge.score = score
            return edge.target
        return self.decide(left_id, right_id, Judgement.NO_JUDGEMENT, score=score)

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
            edge = Edge(left_id, right_id)

        # Canonicalise positive matches, i.e. make both identifiers refer to a
        # canonical identifier, instead of making a direct link.
        if judgement == Judgement.POSITIVE:
            connected = set(self.connected(edge.target))
            connected.update(self.connected(edge.source))
            target = max(connected)
            if not target.canonical:
                canonical = Identifier.make()
                self._remove(edge)
                self.decide(edge.source, canonical, judgement=judgement, user=user)
                self.decide(edge.target, canonical, judgement=judgement, user=user)
                return canonical

        edge.judgement = judgement
        edge.timestamp = datetime.utcnow().isoformat()[:16]
        edge.user = user or getpass.getuser()
        edge.score = score or edge.score
        self._register(edge)
        return edge.target

    def _register(self, edge: Edge) -> None:
        if edge.judgement != Judgement.NO_JUDGEMENT:
            edge.score = None
        self.edges[edge.key] = edge
        self.nodes[edge.source].add(edge)
        self.nodes[edge.target].add(edge)
        self.connected.cache_clear()

    def _remove(self, edge: Edge) -> None:
        """Remove an edge from the graph."""
        self.edges.pop(edge.key, None)
        for node in (edge.source, edge.target):
            if node in self.nodes:
                self.nodes[node].discard(edge)

    def explode(self, node_id: StrIdent) -> Set[str]:
        """Dissolve all edges linked to the cluster to which the node belongs.
        This is the hard way to make sure we re-do context once we realise
        there's been a mistake."""
        node = Identifier.get(node_id)
        affected: Set[str] = set()
        for part in self.connected(node):
            affected.add(str(part))
            edges = self.nodes.get(part)
            if edges is None:
                continue
            for edge in list(edges):
                if edge.judgement != Judgement.NO_JUDGEMENT:
                    self._remove(edge)
        self.connected.cache_clear()
        return affected

    def prune(self, keep: int = 0) -> None:
        """Remove suggested (i.e. NO_JUDGEMENT) edges, keep only the n with the
        highest score. This also checks if a transitive judgement has been
        established in the mean time and removes those candidates."""
        kept = 0
        for edge in self._get_suggested():
            judgement = self.get_judgement(edge.source, edge.target)
            if judgement != Judgement.NO_JUDGEMENT:
                self._remove(edge)
            if kept >= keep:
                self._remove(edge)
            kept += 1
        self.connected.cache_clear()

    def apply(self, proxy: E) -> E:
        """Replace all entity references in a given proxy with their canonical
        identifiers. This is essentially the harmonisation post de-dupe."""
        canonical_id = self.get_canonical(proxy.id)
        if canonical_id != proxy.id:
            proxy.referents = self.get_referents(canonical_id)
            proxy.id = canonical_id
        for prop in proxy.iterprops():
            if prop.type != registry.entity:
                continue
            for value in proxy.pop(prop):
                canonical = self.get_canonical(value)
                proxy.unsafe_add(prop, canonical, cleaned=True)
        return proxy

    def save(self) -> None:
        """Store the resolver adjacency list to a plain text JSON list."""
        if self.path is None:
            raise RuntimeError("Resolver has no path")
        edges = sorted(self.edges.values())
        with open(self.path, "w") as fh:
            for edge in edges:
                fh.write(edge.to_line())

    @classmethod
    def load(cls, path: PathLike) -> "Resolver[E]":
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
