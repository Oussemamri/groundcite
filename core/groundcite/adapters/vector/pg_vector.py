"""Implements VectorIndex (spec §7 step 1a): pgvector HNSW cosine over chunks.embedding.

Dense candidate retrieval: ``embedding <=> %s::vector`` is pgvector's cosine
DISTANCE operator (0 = identical, 2 = opposite), which the HNSW index built in
migration 0001 (``vector_cosine_ops``) serves directly. The port contract wants a
SIMILARITY score where higher is better, so we return ``1 - distance`` — i.e.
cosine similarity in [-1, 1], ~1.0 for a chunk retrieved by its own text.

The query vector is bound as a pgvector TEXT LITERAL (``[0.1,0.2,...]``) and cast
with ``::vector``, the same wire format ``pg_repo`` already uses to write
embeddings. That keeps this adapter dependency-free (no pgvector-python needed
for one cast) and keeps the read and write representations identical by
construction. Adapters stay decoupled from one another (spec §6.1 #4), so the
tiny literal formatter is local rather than imported across adapter packages.

Like pg_repo, the connection opens lazily per call so ``container.build_services``
can construct this adapter with no live DB (CI).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import psycopg

from groundcite.domain.entities import Chunk
from groundcite.ports.protocols import Vector, VectorIndex


class PgVectorIndex(VectorIndex):
    """Dense nearest-neighbour search over chunk embeddings (spec §7 step 1a)."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+psycopg://", "postgresql://")

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn)

    def search(
        self,
        embedding: Vector,
        top_k: int,
        document_slugs: Sequence[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Top-``top_k`` chunks by cosine similarity, optionally restricted to
        the given document slugs (spec §7 filters)."""
        if top_k <= 0:
            return []
        sql = """
            SELECT c.id, c.document_id, c.section_id, c.clause_path, c.content,
                   c.token_count, c.page_start, c.page_end, c.metadata,
                   1 - (c.embedding <=> %(q)s::vector) AS score
              FROM chunks c
        """
        params: dict[str, object] = {"q": _vector_literal(embedding), "k": top_k}
        if document_slugs:
            sql += """
              JOIN documents d ON d.id = c.document_id
             WHERE d.slug = ANY(%(slugs)s)
            """
            params["slugs"] = list(document_slugs)
        # Order by DISTANCE (not the derived score) so the HNSW index is used.
        sql += """
             ORDER BY c.embedding <=> %(q)s::vector
             LIMIT %(k)s
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [(_chunk_from_row(r), float(r[9])) for r in rows]


def _vector_literal(embedding: Vector) -> str:
    """pgvector text format — the same representation pg_repo writes."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


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


def make_pg_vector_index(database_url: str) -> PgVectorIndex:
    """Container factory (spec §4 wiring seam)."""
    return PgVectorIndex(database_url)
