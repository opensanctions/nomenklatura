#
# Don't forget to call self._invalidate from methods that modify edges.
#
import getpass
import logging
from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

from followthemoney.types import registry
from rigour.ids.wikidata import is_qid
from rigour.time import utc_now
from sqlalchemy import (
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    Table,
    Unicode,
    or_,
    text,
)
from sqlalchemy.engine import Connection, Engine, Transaction
from sqlalchemy.sql.expression import delete, insert, update

from nomenklatura.db import get_engine
from nomenklatura.entity import CE
from nomenklatura.judgement import Judgement
from nomenklatura.resolver.edge import Edge
from nomenklatura.resolver.identifier import Identifier, Pair, StrIdent
from nomenklatura.resolver.linker import Linker
from nomenklatura.statement.statement import Statement
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


def timestamp() -> str:
    return utc_now().isoformat()[:28]


class Resolver(Linker[CE]):
    UNDECIDED = (Judgement.NO_JUDGEMENT, Judgement.UNSURE)

    def __init__(
        self,
        engine: Engine,
        metadata: MetaData,
        create: bool = False,
        table_name: str = "resolver",
    ) -> None:
        self._engine = engine
        self._conn: Optional[Connection] = None
        self._transaction: Optional[Transaction] = None
        # Start with None to skip deletes on first BEGIN.
        # We don't have to process deletes to represent the state on first load.
        self._max_ts: Optional[str] = None
        self.edges: Dict[Pair, Edge] = {}
        self.nodes: Dict[Identifier, Set[Edge]] = defaultdict(set)

        unique_kw: Dict[str, Any] = {"unique": True}
        if engine.dialect.name == "sqlite":
            unique_kw["sqlite_where"] = text("deleted_at IS NULL")
        if engine.dialect.name in ("postgresql", "postgres"):
            unique_kw["postgresql_where"] = text("deleted_at IS NULL")
        unique_pair = Index(
            f"{table_name}_source_target_uniq",
            text("source"),
            text("target"),
            **unique_kw,
        )
        self._table = Table(
            table_name,
            metadata,
            Column("id", Integer(), primary_key=True),
            Column("target", Unicode(512), index=True),
            Column("source", Unicode(512), index=True),
            Column("judgement", Unicode(14), nullable=False),
            Column("score", Float, nullable=True),
            Column("user", Unicode(512), nullable=False),
            Column("created_at", Unicode(28)),
            Column("deleted_at", Unicode(28), nullable=True),
            unique_pair,
            extend_existing=True,
        )
        if create:
            metadata.create_all(bind=engine, checkfirst=True, tables=[self._table])

    def _update_from_db(self) -> None:
        """Apply new deletes and unseen edges from the database."""
        stmt = self._table.select()
        if self._max_ts is None:
            stmt = stmt.where(self._table.c.deleted_at.is_(None))
        else:
            stmt = stmt.where(
                or_(
                    self._table.c.deleted_at > self._max_ts,
                    self._table.c.created_at > self._max_ts,
                )
            )
        stmt.order_by(self._table.c.deleted_at.asc().nulls_last())
        stmt.order_by(self._table.c.created_at.asc())
        cursor = self._get_connection().execute(stmt)
        while batch := cursor.fetchmany(10000):
            for row in batch:
                edge = Edge.from_dict(row._mapping)
                if self._max_ts is None:
                    self._max_ts = edge.created_at
                if self._max_ts is not None:
                    if edge.created_at is not None:
                        self._max_ts = max(self._max_ts, edge.created_at)
                    if edge.deleted_at is not None:
                        self._max_ts = max(self._max_ts, edge.deleted_at)
                self._update_edge(edge)
        cursor.close()

    def _update_edge(self, edge: Edge) -> None:
        if edge.deleted_at is None:
            if edge.judgement != Judgement.NO_JUDGEMENT:
                edge.score = None
            self.edges[edge.key] = edge
            self.nodes[edge.source].add(edge)
            self.nodes[edge.target].add(edge)
        else:
            self.edges.pop(edge.key, None)
            for node in (edge.source, edge.target):
                if node in self.nodes:
                    self.nodes[node].discard(edge)
                    if len(self.nodes[node]) == 0:
                        del self.nodes[node]

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
        self._conn = self._engine.connect()
        self._transaction = self._conn.begin()
        self._update_from_db()
        self._invalidate()

    def commit(self) -> None:
        if self._transaction is None or self._conn is None:
            raise RuntimeError("No transaction to commit.")

        # Swipe up all NO JUDGEMENT edges that have been deleted:
        clean_stmt = delete(self._table)
        clean_stmt = clean_stmt.where(
            self._table.c.judgement == Judgement.NO_JUDGEMENT.value
        )
        clean_stmt = clean_stmt.where(self._table.c.deleted_at.is_not(None))
        self._conn.execute(clean_stmt)

        self._transaction.commit()
        self._transaction = None
        self._conn.close()
        self._conn = None

    def rollback(self, force: bool = False) -> None:
        if self._transaction is not None:
            self._transaction.rollback()
            self._transaction = None
        else:
            if not force:
                raise RuntimeError("No transaction to rollback.")
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        else:
            if not force:
                raise RuntimeError("No connection to close.")

    def _get_connection(self) -> Connection:
        if self._transaction is None or self._conn is None:
            raise RuntimeError("No transaction in progress.")
        return self._conn

    def get_linker(self) -> Linker[CE]:
        """Return a linker object that can be used to resolve entities.
        This is less memory-consuming than the full resolver object.
        """
        entities: Dict[Identifier, Set[Identifier]] = {}
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.judgement == Judgement.POSITIVE.value)
        stmt = stmt.where(self._table.c.deleted_at.is_(None))
        stmt.order_by(self._table.c.created_at.asc())
        with self._engine.connect() as conn:
            cursor = conn.execute(stmt)
            while batch := cursor.fetchmany(20000):
                for row in batch:
                    edge = Edge.from_dict(row._mapping)
                    cluster = entities.get(edge.source)
                    if cluster is None:
                        cluster = set([edge.source])
                    other = entities.get(edge.target)
                    if other is None:
                        other = set([edge.target])
                    cluster.update(other)
                    for node in cluster:
                        entities[node] = cluster
            cursor.close()
        return Linker(entities)

    def get_edge(self, left_id: StrIdent, right_id: StrIdent) -> Optional[Edge]:
        key = Identifier.pair(left_id, right_id)
        return self.edges.get(key)

    def _traverse(self, node: Identifier, seen: Set[Identifier]) -> Set[Identifier]:
        """Returns the set of nodes connected to the given node via positive judgement."""
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

    @lru_cache(maxsize=200000)
    def get_canonical(self, entity_id: StrIdent) -> str:
        """Return the canonical identifier for the given entity ID."""
        node = Identifier.get(entity_id)
        max_ = max(self.connected(node))
        if max_.canonical:
            return max_.id
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
        """
        Return _some_ edge that connects the two entities, if it exists.
        """
        (left, right) = Identifier.pair(left_id, right_id)
        left_connected = self.connected(left)
        right_connected = self.connected(right)
        for e in left_connected:
            for o in right_connected:
                if e == o:
                    continue
                edge = self.edges.get(Identifier.pair(e, o))
                if edge is None:
                    continue
                return edge
        return None

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
        if is_qid(entity.id) and is_qid(other.id):
            return Judgement.NEGATIVE

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

        return Judgement.NO_JUDGEMENT

    def check_candidate(self, left: StrIdent, right: StrIdent) -> bool:
        """Check if the two IDs could be merged, i.e. if there's no existing
        judgement."""
        judgement = self.get_judgement(left, right)
        return judgement == Judgement.NO_JUDGEMENT

    def get_judgements(
        self, limit: Optional[int] = None
    ) -> Generator[Edge, None, None]:
        """Get most recently updated edges other than NO_JUDGEMENT."""
        stmt = self._table.select()
        stmt = stmt.where(self._table.c.judgement != Judgement.NO_JUDGEMENT.value)
        stmt = stmt.where(self._table.c.deleted_at.is_(None))
        stmt = stmt.order_by(self._table.c.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        cursor = self._get_connection().execute(stmt)
        while batch := cursor.fetchmany(25):
            for row in batch:
                yield Edge.from_dict(row._mapping)
        cursor.close()

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
                # Just update score

                # database
                stmt = update(self._table)
                stmt = stmt.where(self._table.c.target == edge.target.id)
                stmt = stmt.where(self._table.c.source == edge.source.id)
                stmt = stmt.where(self._table.c.deleted_at.is_(None))
                stmt = stmt.where(
                    self._table.c.judgement == Judgement.NO_JUDGEMENT.value
                )
                stmt = stmt.values({"score": score})
                self._get_connection().execute(stmt)

                # local state
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
        edge.created_at = timestamp()
        edge.user = user or getpass.getuser()
        edge.score = score or edge.score
        self._register(edge)
        if judgement != Judgement.NO_JUDGEMENT:
            self._invalidate()
        return edge.target

    def _register(self, edge: Edge) -> None:
        """Ensure the edge exists in the resolver, as provided."""
        if edge.judgement != Judgement.NO_JUDGEMENT:
            edge.score = None

        ustmt = update(self._table)
        ustmt = ustmt.values({"deleted_at": timestamp()})
        ustmt = ustmt.where(self._table.c.source == edge.source.id)
        ustmt = ustmt.where(self._table.c.target == edge.target.id)
        ustmt = ustmt.where(self._table.c.deleted_at.is_(None))
        self._get_connection().execute(ustmt)

        stmt = insert(self._table).values(edge.to_dict())
        self._get_connection().execute(stmt)
        self._update_edge(edge)

    def _remove_edge(self, edge: Edge) -> None:
        """Remove an edge from the graph."""
        edge.deleted_at = timestamp()
        stmt = update(self._table)
        stmt = stmt.values({"deleted_at": edge.deleted_at})
        stmt = stmt.where(self._table.c.target == edge.target.id)
        stmt = stmt.where(self._table.c.source == edge.source.id)
        stmt = stmt.where(self._table.c.deleted_at.is_(None))
        self._get_connection().execute(stmt)
        self._update_edge(edge)

    def _remove_node(self, node: Identifier) -> None:
        """Remove a node from the graph."""
        deleted_at = timestamp()
        stmt = update(self._table)
        stmt = stmt.values({"deleted_at": deleted_at})
        cond = or_(
            self._table.c.source == node.id,
            self._table.c.target == node.id,
        )
        stmt = stmt.where(cond)
        stmt = stmt.where(self._table.c.deleted_at.is_(None))
        self._get_connection().execute(stmt)

        edges = self.nodes.get(node)
        if edges is None:
            return
        for edge in list(edges):
            edge.deleted_at = deleted_at
            if edge.judgement != Judgement.NO_JUDGEMENT:
                self._update_edge(edge)

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
        """Remove suggested (i.e. NO_JUDGEMENT) edges."""
        # database
        stmt = delete(self._table)
        stmt = stmt.where(self._table.c.judgement == Judgement.NO_JUDGEMENT.value)
        self._get_connection().execute(stmt)

        # local state
        now = timestamp()
        for edge in list(self.edges.values()):
            if edge.judgement == Judgement.NO_JUDGEMENT:
                edge.deleted_at = now
                self._update_edge(edge)

    def apply_statement(self, stmt: Statement) -> Statement:
        """Canonicalise Statement Entity IDs and ID values"""
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

    def dump(self, path: PathLike) -> None:
        """Store the resolver adjacency list to a plain text JSON list."""
        edges = sorted(self.edges.values())
        with open(path, "w") as fh:
            for edge in edges:
                fh.write(edge.to_line())

    def load(self, path: PathLike) -> None:
        """Load edges directly into the database"""
        edge_count = 0
        with open(path, "r") as fh:
            while True:
                line = fh.readline()
                if not line:
                    break
                edge = Edge.from_line(line)
                self._register(edge)
                edge_count += 1
                if edge_count % 10000 == 0:
                    log.info("Loaded %s edges." % edge_count)
        log.info("Done. Loaded %s edges." % edge_count)
        self._invalidate()

    def __repr__(self) -> str:
        parts = self._engine.url
        url = f"{parts.drivername}://{parts.host or ""}/{parts.database}/{self._table.name}"
        return f"<Resolver({url})>"
