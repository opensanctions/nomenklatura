import getpass
import logging
from functools import lru_cache
from typing import Dict, Generator, Optional, Set, Tuple
from urllib.parse import urlunparse

from followthemoney.types import registry
from rigour.ids.wikidata import is_qid
from rigour.time import utc_now
from sqlalchemy import Column, Float, MetaData, Table, Unicode, alias, func, or_
from sqlalchemy.engine import Connection, Engine, Transaction
from sqlalchemy.sql.expression import delete, select, update

from nomenklatura.db import get_engine, get_upsert_func
from nomenklatura.entity import CE
from nomenklatura.judgement import Judgement
from nomenklatura.resolver.edge import Edge
from nomenklatura.resolver.identifier import Identifier, StrIdent
from nomenklatura.resolver.linker import Linker
from nomenklatura.statement.statement import Statement
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


class Resolver(Linker[CE]):
    UNDECIDED = (Judgement.NO_JUDGEMENT, Judgement.UNSURE)

    def __init__(
        self,
        engine: Engine,
        metadata: MetaData,
        create: bool = False,
        table_name: str = "resolver",
    ) -> None:
        self._upsert = get_upsert_func(engine)
        self._engine = engine
        self._conn: Optional[Connection] = None
        self._transaction: Optional[Transaction] = None
        self._table = Table(
            table_name,
            metadata,
            Column("target", Unicode(512), index=True, primary_key=True),
            Column("source", Unicode(512), index=True, primary_key=True),
            Column("judgement", Unicode(14), nullable=False),
            Column("score", Float, nullable=True),
            Column("user", Unicode(512), nullable=False),
            Column("timestamp", Unicode(28)),
            extend_existing=True,
        )
        if create:
            metadata.create_all(bind=engine, checkfirst=True)

    @classmethod
    def make_default(cls, engine: Optional[Engine] = None) -> "Resolver[CE]":
        if engine is None:
            engine = get_engine()
        meta = MetaData()
        return cls(engine, meta, create=True)

    def _invalidate(self) -> None:
        self.connected.cache_clear()
        self.get_canonical.cache_clear()

    def begin(self) -> None:
        """
        Start a new transaction in Begin Once style. Callers are responsible for
        committing or rolling back the transaction.

        https://docs.sqlalchemy.org/en/20/core/connections.html#begin-once
        """
        if self._conn is not None or self._transaction is not None:
            log.warning("Transaction already open: %s", self)
            return
        self._invalidate()
        self._conn = self._engine.connect()
        self._transaction = self._conn.begin()

    def commit(self) -> None:
        if self._transaction is None or self._conn is None:
            raise RuntimeError("No transaction to commit.")
        self._transaction.commit()
        self._transaction = None
        self._conn.close()
        self._conn = None

    def rollback(self) -> None:
        if self._transaction is None or self._conn is None:
            raise RuntimeError("No transaction to rollback.")
        self._transaction.rollback()
        self._transaction = None
        self._conn.close()
        self._conn = None

    def _get_connection(self) -> Connection:
        if self._transaction is None or self._conn is None:
            raise RuntimeError("No transaction in progress.")
        return self._conn

    def get_linker(self) -> Linker[CE]:
        """Return a linker object that can be used to resolve entities.
        This is less memory-consuming than the full resolver object.
        """
        clusters: Dict[Identifier, Set[Identifier]] = {}
        stmt = select(self._table)
        stmt = stmt.where(self._table.c.judgement == Judgement.POSITIVE.value)
        for row in self._get_connection().execute(stmt).fetchall():
            edge = Edge.from_dict(row._mapping)
            cluster = clusters.get(edge.target, set())
            cluster.update(clusters.get(edge.source, [edge.source]))
            cluster.add(edge.target)
            for node in cluster:
                clusters[node] = cluster
        log.info("Loaded %s clusters from: %s", len(clusters), self)
        return Linker(clusters)

    def get_edge(self, left_id: StrIdent, right_id: StrIdent) -> Optional[Edge]:
        """Get an edge matching the given keys in any direction, if it exists."""

        key = Identifier.pair(left_id, right_id)
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.target == key[0].id)
        stmt = stmt.where(self._table.c.source == key[1].id)
        res = self._get_connection().execute(stmt).fetchone()
        if res is None:
            return None
        return Edge.from_dict(res._mapping)

    def get_edges(self) -> Set[Edge]:
        stmt = select(self._table)
        edges = set()
        for row in self._get_connection().execute(stmt).fetchall():
            edges.add(Edge.from_dict(row._mapping))
        return edges

    @lru_cache(maxsize=200000)
    def connected(self, node: Identifier) -> Set[Identifier]:
        """
        WITH RECURSIVE connected AS (
            SELECT r.target AS node_id
                FROM resolver r
                WHERE r.source = 'Q7747' AND r.judgement = 'positive'
            UNION
            SELECT r.source AS node_id
                FROM resolver r
                WHERE r.target = 'Q7747' AND r.judgement = 'positive'
            UNION
            SELECT r.source AS node_id
                FROM connected c LEFT JOIN resolver r
                WHERE r.target = c.node_id AND r.judgement = 'positive'
            UNION
            SELECT r.target_id AS node_id
                FROM connected c LEFT JOIN resolver r
                WHERE r.source = c.node_id AND r.judgement = 'positive'
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
        for row in self._get_connection().execute(stmt).fetchall():
            connected.add(Identifier(row.node))
        return connected

    @lru_cache(maxsize=200000)
    def get_canonical(self, entity_id: StrIdent) -> str:
        """Return the canonical identifier for the given entity ID."""
        node = Identifier.get(entity_id)
        best = max(self.connected(node))
        if best.canonical:
            return best.id
        return node.id

    def canonicals(self) -> Generator[Identifier, None, None]:
        """Return all the canonical cluster identifiers."""
        col = func.distinct(self._table.c.target)
        stmt = select(col.label("node"))
        stmt = stmt.where(self._table.c.judgement == Judgement.POSITIVE.value)
        rows = self._get_connection().execute(stmt).fetchall()
        seen: Set[Identifier] = set()
        for row in rows:
            node = Identifier(row.node)
            if not node.canonical or node in seen:
                continue
            connected = self.connected(node)
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

    def _get_resolved_edges(
        self, left_id: StrIdent, right_id: StrIdent
    ) -> Generator[Edge, None, None]:
        (left, right) = Identifier.pair(left_id, right_id)
        left_connected = self.connected(left)
        right_connected = self.connected(right)
        for e in left_connected:
            for o in right_connected:
                if e == o:
                    continue
                edge = self.get_edge(e, o)
                if edge is None:
                    continue
                yield edge

    def get_resolved_edge(
        self, left_id: StrIdent, right_id: StrIdent
    ) -> Optional[Edge]:
        """Some edge between left and right, if any."""
        return next(self._get_resolved_edges(left_id, right_id), None)

    def _pair_judgement(self, left: Identifier, right: Identifier) -> Judgement:
        edge = self.get_edge(left, right)
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

    def get_judgements(self, limit: Optional[int] = None) -> Generator[Edge, None, None]:
        """Get most recently updated edges other than NO_JUDGEMENT."""
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.judgement != Judgement.NO_JUDGEMENT.value)
        stmt = stmt.order_by(self._table.c.timestamp.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        cursor = self._get_connection().execute(stmt)
        while batch := cursor.fetchmany(25):
            for row in batch:
                yield Edge.from_dict(row._mapping)

    def _get_suggested(self) -> Generator[Edge, None, None]:
        """Get all NO_JUDGEMENT edges in descending order of score."""
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.judgement == Judgement.NO_JUDGEMENT.value)
        stmt = stmt.where(self._table.c.score != None)  # noqa
        stmt = stmt.order_by(self._table.c.score.desc())
        cursor = self._get_connection().execute(stmt)
        while batch := cursor.fetchmany(25):
            for row in batch:
                yield Edge.from_dict(row._mapping)

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
                stmt = update(self._table)
                stmt = stmt.where(self._table.c.target == edge.target.id)
                stmt = stmt.where(self._table.c.source == edge.source.id)
                stmt = stmt.values({"score": score})
                self._get_connection().execute(stmt)
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
        timestamp: Optional[str] = None,
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
        edge.timestamp = timestamp or utc_now().isoformat()[:28]
        edge.user = user or getpass.getuser()
        edge.score = score or edge.score
        self._register(edge)
        self._invalidate()
        return edge.target

    def _register(self, edge: Edge) -> None:
        """Ensure the edge exists in the resolver, as provided."""
        if edge.judgement != Judgement.NO_JUDGEMENT:
            edge.score = None
        istmt = self._upsert(self._table).values(edge.to_dict())
        update_values = dict(
            judgement=istmt.excluded.judgement,
            score=istmt.excluded.score,
            user=istmt.excluded.user,
            timestamp=istmt.excluded.timestamp,
        )
        stmt = istmt.on_conflict_do_update(
            index_elements=["source", "target"], set_=update_values
        )
        self._get_connection().execute(stmt)

    def _remove_edge(self, edge: Edge) -> None:
        """Remove an edge from the graph."""
        stmt = delete(self._table)
        stmt = stmt.where(self._table.c.target == edge.target.id)
        stmt = stmt.where(self._table.c.source == edge.source.id)
        self._get_connection().execute(stmt)

    def _remove_node(self, node: Identifier) -> None:
        """Remove a node from the graph."""
        stmt = delete(self._table)
        cond = or_(
            self._table.c.source == node.id,
            self._table.c.target == node.id,
        )
        stmt = stmt.where(cond)
        self._get_connection().execute(stmt)

    def remove(self, node_id: StrIdent) -> None:
        """Remove all edges linking to the given node from the graph."""
        node = Identifier.get(node_id)
        self._remove_node(node)
        self._invalidate()

    def explode(self, node_id: StrIdent) -> Set[str]:
        """Dissolve all edges linked to the cluster to which the node belongs.
        This is the hard way to make sure we re-do context once we realise
        there's been a mistake."""
        node = Identifier.get(node_id)
        affected: Set[str] = set()
        for part in self.connected(node):
            affected.add(str(part))
            self._remove_node(part)
        self._invalidate()
        return affected

    def prune(self) -> None:
        """Remove suggested (i.e. NO_JUDGEMENT) edges, keep only the n with the
        highest score. This also checks if a transitive judgement has been
        established in the mean time and removes those candidates."""
        stmt = delete(self._table)
        stmt = stmt.where(self._table.c.judgement == Judgement.NO_JUDGEMENT.value)
        self._get_connection().execute(stmt)
        self._invalidate()

    def apply_statement(self, stmt: Statement) -> Statement:
        if stmt.entity_id is not None:
            stmt.canonical_id = self.get_canonical(stmt.entity_id)
        if stmt.prop_type == registry.entity.name:
            canon_value = self.get_canonical(stmt.value)
            if canon_value != stmt.value:
                if stmt.original_value is None:
                    stmt.original_value = stmt.value
                # NOTE: this means the key is out of whack here now
                stmt.value = canon_value
        return stmt

    def save(self, path: PathLike) -> None:
        """Store the resolver adjacency list to a plain text JSON list."""
        with open(path, "w") as fh:
            res = self._get_connection().execute(select(self._table))
            while True:
                rows = res.fetchmany(10000)
                if rows is None or not len(rows):
                    break
                for row in rows:
                    edge = Edge.from_dict(row._mapping)
                    line = edge.to_line()
                    fh.write(line)

    def load(self, path: PathLike) -> None:
        """Load edges directly into the database"""
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                edge = Edge.from_line(line)
                # There exist legacy positive edges which don't lead to a canonical.
                # If we load these edges using self.decide, some of them generate
                # canonicals which are greater than the current canonicals connected
                # to these edges. This could imply lots of unplanned rekeying.
                # So let's just register the edges as they are for now.
                self._register(edge)

    def __repr__(self) -> str:
        parts = self._engine.url
        url = urlunparse(
            (
                parts.drivername,
                parts.host,
                f"/{parts.database}/{self._table.name}",
                None,
                None,
                None,
            )
        )
        return f"<Resolver({url})>"
