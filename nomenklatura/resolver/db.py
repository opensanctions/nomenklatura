import getpass
from pathlib import Path
from datetime import datetime
from functools import lru_cache
from typing import Generator, Optional, Set, Tuple
from followthemoney.types import registry
from sqlalchemy import MetaData, or_, alias, func
from sqlalchemy import Table, Column, Unicode, Float
from sqlalchemy.engine import Engine
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete
from sqlalchemy.dialects.postgresql import insert as upsert

from nomenklatura.entity import CE
from nomenklatura.judgement import Judgement
from nomenklatura.db import get_engine, get_metadata, ensure_tx, Conn
from nomenklatura.resolver.identifier import Identifier, StrIdent
from nomenklatura.resolver.edge import Edge
from nomenklatura.resolver.resolver import Resolver
from nomenklatura.util import PathLike, is_qid


class DatabaseResolver(Resolver[CE]):
    """A graph of entity identity judgements, used to compute connected components
    to determine canonical IDs for entities."""

    def __init__(
        self, engine: Engine, metadata: MetaData, create: bool = False
    ) -> None:
        self._engine = engine
        self._table = Table(
            "resolver",
            metadata,
            Column(
                "target", Unicode(512), index=True, nullable=False, primary_key=True
            ),
            Column(
                "source", Unicode(512), index=True, nullable=False, primary_key=True
            ),
            Column("judgement", Unicode(14), nullable=False),
            Column("score", Float, nullable=True),
            Column("user", Unicode(512), nullable=False),
            Column("timestamp", Unicode(28)),
            extend_existing=True,
        )
        if create:
            metadata.create_all(checkfirst=True)

    def get_edge(
        self, left_id: StrIdent, right_id: StrIdent, conn_: Conn = None
    ) -> Optional[Edge]:
        key = Identifier.pair(left_id, right_id)
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.target == key[0].id)
        stmt = stmt.where(self._table.c.source == key[1].id)
        with ensure_tx(conn_) as conn:
            res = conn.execute(stmt).fetchone()
            if res is None:
                return None
            return Edge.from_dict(res)

    @lru_cache(maxsize=None)
    def connected(self, node: Identifier, conn_: Conn = None) -> Set[Identifier]:
        """
        WITH RECURSIVE connected AS (
            SELECT r.target_id AS node_id
                FROM resolver r
                WHERE r.source_id = 'Q7747' AND r.judgement = 'positive'
            UNION
            SELECT r.source_id AS node_id
                FROM resolver r
                WHERE r.target_id = 'Q7747' AND r.judgement = 'positive'
            UNION
            SELECT r.source_id AS node_id
                FROM connected c LEFT JOIN resolver r
                WHERE r.target_id = c.node_id AND r.judgement = 'positive'
            UNION
            SELECT r.target_id AS node_id
                FROM connected c LEFT JOIN resolver r
                WHERE r.source_id = c.node_id AND r.judgement = 'positive'
        )
        SELECT node_id FROM connected;
        """
        positive = Judgement.POSITIVE.value
        rslv = alias(self._table, "r")
        target = rslv.c.target
        source = rslv.c.source
        judgement = rslv.c.judgement
        stmt_t = select(target.label("node"))
        stmt_t = stmt_t.where(source == node.id, judgement == positive)
        cte = stmt_t.cte("connected", recursive=True)
        cte_alias = cte.alias("c")
        stmt_s = select(source.label("node"))
        stmt_s = stmt_s.where(target == node.id, judgement == positive)
        stmt_rs = select(source.label("node"))
        stmt_rs = stmt_rs.join(cte_alias, cte_alias.c.node == target)
        stmt_rs = stmt_rs.where(judgement == positive)
        stmt_rt = select(target.label("node"))
        stmt_rt = stmt_rt.join(cte_alias, cte_alias.c.node == source)
        stmt_rt = stmt_rt.where(judgement == positive)
        cte = cte.union(stmt_s, stmt_rs, stmt_rt)  # type: ignore

        stmt = select(cte.c.node)
        connected = set([node])
        with ensure_tx(conn_) as conn:
            for row in conn.execute(stmt).fetchall():
                connected.add(Identifier(row.node))
        return connected

    def get_canonical(self, entity_id: StrIdent) -> str:
        """Return the canonical identifier for the given entity ID."""
        node = Identifier.get(entity_id)
        best = max(self.connected(node))
        if best.canonical:
            return best.id
        return node.id

    def canonicals(self, _conn: Conn = None) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        col = func.distinct(self._table.c.target)
        stmt = self._table.select(col.alias("node"))
        stmt = stmt.where(self._table.c.judgement == Judgement.POSITIVE.value)
        with ensure_tx(_conn) as conn:
            rows = conn.execute(stmt).fetchall()

        seen: Set[Identifier] = set()
        for row in rows:
            node = Identifier(row.node)
            if not node.canonical or node in seen:
                continue
            connected = self.connected(node, _conn=conn)
            for linked in connected:
                if linked.canonical:
                    seen.add(linked)
            yield max(connected)

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
                if edge is not None:
                    return edge
        return None

    def _pair_judgement(
        self, left: Identifier, right: Identifier, conn_: Conn = None
    ) -> Judgement:
        edge = self.get_edge(left, right, conn_=conn_)
        if edge is not None:
            return edge.judgement
        return Judgement.NO_JUDGEMENT

    def get_judgement(
        self, entity_id: StrIdent, other_id: StrIdent, conn_: Conn = None
    ) -> Judgement:
        """Get the existing decision between two entities with dedupe factored in."""
        entity = Identifier.get(entity_id)
        other = Identifier.get(other_id)
        if entity == other:
            return Judgement.POSITIVE
        entity_connected = self.connected(entity, conn_=conn_)
        if other in entity_connected:
            return Judgement.POSITIVE

        other_connected = self.connected(other, conn_=conn_)
        for e in entity_connected:
            for o in other_connected:
                judgement = self._pair_judgement(e, o, conn_=conn_)
                if judgement != Judgement.NO_JUDGEMENT:
                    return judgement

        if is_qid(entity.id) and is_qid(other.id):
            return Judgement.NEGATIVE
        return Judgement.NO_JUDGEMENT

    def check_candidate(
        self, left: StrIdent, right: StrIdent, conn_: Conn = None
    ) -> bool:
        """Check if the two IDs could be merged, i.e. if there's no existing
        judgement."""
        judgement = self.get_judgement(left, right, conn_=conn_)
        return judgement == Judgement.NO_JUDGEMENT

    def _get_suggested(self, conn_: Conn = None) -> Generator[Edge, None, None]:
        """Get all NO_JUDGEMENT edges in descending order of score."""
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.judgement == Judgement.NO_JUDGEMENT.value)
        stmt = stmt.where(self._table.c.score != None)
        stmt = stmt.order_by(self._table.c.score.desc())
        with ensure_tx(conn_) as conn:
            cursor = conn.execute(stmt)
            while batch := cursor.fetchmany(25):
                for row in batch:
                    yield Edge.from_dict(row)

    def get_candidates(
        self, limit: Optional[int] = None, conn_: Conn = None
    ) -> Generator[Tuple[str, str, Optional[float]], None, None]:
        returned = 0
        for edge in self._get_suggested(conn_=conn_):
            if not self.check_candidate(edge.source, edge.target, conn_=conn_):
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
        conn_: Conn = None,
    ) -> Identifier:
        """Make a NO_JUDGEMENT link between two identifiers to suggest that a user
        should make a decision about whether they are the same or not."""
        edge = self.get_edge(left_id, right_id, conn_=conn_)
        if edge is not None:
            if edge.judgement == Judgement.NO_JUDGEMENT:
                edge.score = score
            return edge.target
        return self.decide(
            left_id,
            right_id,
            Judgement.NO_JUDGEMENT,
            score=score,
            user=user,
            conn_=conn_,
        )

    def decide(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        judgement: Judgement,
        user: Optional[str] = None,
        score: Optional[float] = None,
        conn_: Conn = None,
    ) -> Identifier:
        edge = self.get_edge(left_id, right_id, conn_=conn_)
        if edge is None:
            edge = Edge(left_id, right_id, judgement=judgement)

        # Canonicalise positive matches, i.e. make both identifiers refer to a
        # canonical identifier, instead of making a direct link.
        if judgement == Judgement.POSITIVE:
            connected = set(self.connected(edge.target, conn_=conn_))
            connected.update(self.connected(edge.source, conn_=conn_))
            target = max(connected)
            if not target.canonical:
                canonical = Identifier.make()
                self._remove_edge(edge, conn_=conn_)
                self.decide(
                    edge.source, canonical, judgement=judgement, user=user, conn_=conn_
                )
                self.decide(
                    edge.target, canonical, judgement=judgement, user=user, conn_=conn_
                )
                return canonical

        edge.judgement = judgement
        edge.timestamp = datetime.utcnow().isoformat()[:16]
        edge.user = user or getpass.getuser()
        edge.score = score or edge.score
        self._register(edge, conn_=conn_)
        self.connected.cache_clear()
        return edge.target

    def _register(self, edge: Edge, conn_: Conn = None) -> None:
        if edge.judgement != Judgement.NO_JUDGEMENT:
            edge.score = None
        istmt = upsert(self._table).values([edge.to_dict()])
        values = dict(
            judgement=istmt.excluded.judgement,
            score=istmt.excluded.score,
            user=istmt.excluded.user,
            timestamp=istmt.excluded.timestamp,
        )
        stmt = istmt.on_conflict_do_update(
            index_elements=["source_id", "target_id"], set_=values
        )
        with ensure_tx(conn_) as conn:
            conn.execute(stmt)

    def _remove_edge(self, edge: Edge, conn_: Conn = None) -> None:
        """Remove an edge from the graph."""
        stmt = delete(self._table)
        stmt = stmt.where(self._table.c.source == edge.source.id)
        stmt = stmt.where(self._table.c.target == edge.target.id)
        with ensure_tx(conn_) as conn:
            conn.execute(stmt)

    def _remove_node(self, node: Identifier, conn_: Conn = None) -> None:
        """Remove a node from the graph."""
        stmt = delete(self._table)
        cond = or_(
            self._table.c.source == node.id,
            self._table.c.target == node.id,
        )
        stmt = stmt.where(cond)
        with ensure_tx(conn_) as conn:
            conn.execute(stmt)

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
        stmt = delete(self._table)
        stmt = stmt.where(self._table.c.judgement == Judgement.NO_JUDGEMENT.value)
        with ensure_tx() as conn:
            conn.execute(stmt)
        self.connected.cache_clear()

    def apply(self, proxy: CE) -> CE:
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
        raise NotImplemented

    def merge(self, path: PathLike) -> None:
        with ensure_tx() as conn:
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
                        conn_=conn,
                    )

    @classmethod
    def load(cls, path: Path) -> "Resolver[CE]":
        raise NotImplemented

    @classmethod
    def make_default(cls) -> "Resolver[CE]":
        engine = get_engine()
        meta = get_metadata()
        return cls(engine, meta, create=True)

    def __repr__(self) -> str:
        return f"<Resolver({self._table!r})>"
