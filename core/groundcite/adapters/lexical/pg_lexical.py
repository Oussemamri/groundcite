"""Implements LexicalIndex (spec §7 steps 1b/1c): Postgres tsvector
ts_rank_cd search plus the exact clause_path fast path.

``search`` (§7 step 1b) ranks with ``ts_rank_cd(tsv, websearch_to_tsquery(...))``
against the generated ``tsv`` column and its GIN index (migration 0001). The
``@@`` predicate is what lets the GIN index do the work; ts_rank_cd only orders
the matches. ``websearch_to_tsquery`` is used (not ``plainto_tsquery``) because it
tolerates real user question text — quotes, OR, negation — without raising.

``match_clause`` (§7 step 1c) is the clause-ID fast path: an exact hit that the
fusion step injects at rank 1. It accepts EITHER a full clause_path
("14 CFR Part 25 §25.1309") or a bare clause id ("25.1309(b)"), because the
question-side detector (services/clause_detect) recovers the clause id only — it
cannot know which standard the asker meant. Matching is exact on the §-suffix
(``split_part``), never a LIKE wildcard, so "25.100" can never match "25.1001".

NOTE (language): the ``tsv`` column is generated with the 'english' config, so
German questions retrieve poorly on this path by construction. That is expected
in v1 and is measured, not hidden — dense (multilingual bge-m3) carries the
German suite. A ``tsv_de`` column is the spec §5/§16 extension path.

Like pg_repo, the connection opens lazily per call so ``container.build_services``
can construct this adapter with no live DB (CI).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import psycopg

from groundcite.domain.entities import Chunk
from groundcite.ports.protocols import LexicalIndex

_CHUNK_COLUMNS = """c.id, c.document_id, c.section_id, c.clause_path, c.content,
                    c.token_count, c.page_start, c.page_end, c.metadata"""


class PgLexicalIndex(LexicalIndex):
    """Full-text search + exact clause-path fast path (spec §7 steps 1b, 1c)."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+psycopg://", "postgresql://")

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn)

    def search(
        self,
        query: str,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Top-``top_k`` chunks by ts_rank_cd (spec §7 step 1b)."""
        if top_k <= 0 or not query.strip():
            return []
        sql = f"""
            SELECT {_CHUNK_COLUMNS},
                   ts_rank_cd(c.tsv, websearch_to_tsquery('english', %(q)s)) AS score
              FROM chunks c
        """
        params: dict[str, object] = {"q": query, "k": top_k}
        where = ["c.tsv @@ websearch_to_tsquery('english', %(q)s)"]
        if document_slugs:
            sql += " JOIN documents d ON d.id = c.document_id"
            where.append("d.slug = ANY(%(slugs)s)")
            params["slugs"] = list(document_slugs)
        sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY score DESC LIMIT %(k)s"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(_chunk_from_row(r), float(r[9])) for r in rows]

    def match_clause(
        self, clause_path: str, document_slugs: Sequence[str] | None = None
    ) -> list[Chunk]:
        """Exact clause-ID fast path (spec §7 step 1c). Returns every chunk of
        the matching clause (a long clause splits into several chunks), ordered
        stably so the fused rank-1 injection is deterministic."""
        clause_id = _clause_id_of(clause_path)
        if not clause_id:
            return []
        sql = f"""
            SELECT {_CHUNK_COLUMNS}
              FROM chunks c
        """
        params: dict[str, object] = {"raw": clause_path, "id": clause_id}
        where = ["(c.clause_path = %(raw)s OR split_part(c.clause_path, '§', 2) = %(id)s)"]
        if document_slugs:
            sql += " JOIN documents d ON d.id = c.document_id"
            where.append("d.slug = ANY(%(slugs)s)")
            params["slugs"] = list(document_slugs)
        sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.page_start NULLS LAST, c.id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_chunk_from_row(r) for r in rows]


def _clause_id_of(clause_path: str) -> str:
    """The clause id from either a full clause_path or a bare id.

    '14 CFR Part 25 §25.1309' -> '25.1309';  '25.1309(b)' -> '25.1309(b)'.
    """
    return clause_path.rsplit("§", 1)[-1].strip()


def _chunk_from_row(row: Sequence[Any]) -> Chunk:
    return Chunk(
        id=row[0],
        document_id=row[1],
        section_id=row[2],
        clause_path=row[3],
        content=row[4],
        token_count=row[5],
        page_start=row[6],
        page_end=row[7],
        metadata=json.loads(row[8]) if row[8] else {},
    )


def make_pg_lexical_index(database_url: str) -> PgLexicalIndex:
    """Container factory (spec §4 wiring seam)."""
    return PgLexicalIndex(database_url)
