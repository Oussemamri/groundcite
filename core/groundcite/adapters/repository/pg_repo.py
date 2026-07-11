"""Implements Repository (spec §5): Postgres persistence for documents,
sections, chunks, asks, citations, and evals, via psycopg3.

Uses the raw DB-API (no ORM) so the §5 schema stays the single source of truth
and the one-transaction idempotent re-ingest (spec §6) is a literal BEGIN →
DELETE → INSERT → COMMIT. The connection is opened lazily per call so
``container.build_services`` can construct this adapter without a live DB (CI).

The SQLAlchemy-style DATABASE_URL (``postgresql+psycopg://...``) is normalized
to the bare ``postgresql://...`` DSN psycopg expects.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import psycopg

from groundcite.domain.entities import Ask, Chunk, Document, EvalCase, Section
from groundcite.domain.results import EvalRun


class PgRepository:
    """Postgres Repository (spec §5, §6 idempotency)."""

    def __init__(self, database_url: str) -> None:
        self._dsn = database_url.replace("postgresql+psycopg://", "postgresql://")

    # --- helpers ---------------------------------------------------------

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._dsn)

    # --- documents -------------------------------------------------------

    def upsert_document(self, document: Document) -> Document:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO documents
                  (id, slug, standard_code, title, organization, version,
                   language, source_url, license_note, ingested_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (slug) DO UPDATE SET
                  standard_code = EXCLUDED.standard_code,
                  title          = EXCLUDED.title,
                  organization   = EXCLUDED.organization,
                  version        = EXCLUDED.version,
                  language       = EXCLUDED.language,
                  source_url     = EXCLUDED.source_url,
                  license_note   = EXCLUDED.license_note,
                  ingested_at    = now()
                RETURNING id, slug, standard_code, title, organization, version,
                          language, source_url, license_note, ingested_at
                """,
                (
                    document.id,
                    document.slug,
                    document.standard_code,
                    document.title,
                    document.organization,
                    document.version,
                    document.language,
                    document.source_url,
                    document.license_note,
                ),
            ).fetchone()
        return _document_from_row(row)

    def get_document(self, slug: str) -> Document | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, slug, standard_code, title, organization, version,
                          language, source_url, license_note, ingested_at
                   FROM documents WHERE slug = %s""",
                (slug,),
            ).fetchone()
        return _document_from_row(row) if row else None

    def list_documents(self) -> list[Document]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, slug, standard_code, title, organization, version,
                          language, source_url, license_note, ingested_at
                   FROM documents ORDER BY slug"""
            ).fetchall()
        return [_document_from_row(r) for r in rows]

    # --- sections + chunks (one-transaction replace, spec §6 idempotency) --

    def replace_sections_and_chunks(
        self, document_id: UUID, sections: Sequence[Section], chunks: Sequence[Chunk]
    ) -> None:
        # Parent rows (lower level) are inserted before children so the
        # self-FK sections.parent_id is satisfiable within the transaction.
        ordered = sorted(sections, key=lambda s: (s.level, s.ordinal))
        with self._connect() as conn, conn.transaction():
            conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            conn.execute("DELETE FROM sections WHERE document_id = %s", (document_id,))
            with conn.cursor() as cur:
                if ordered:
                    cur.executemany(
                        """INSERT INTO sections
                                 (id, document_id, parent_id, clause_id, title, level, ordinal)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        [
                            (
                                s.id,
                                s.document_id,
                                s.parent_id,
                                s.clause_id,
                                s.title,
                                s.level,
                                s.ordinal,
                            )
                            for s in ordered
                        ],
                    )
                if chunks:
                    cur.executemany(
                        """INSERT INTO chunks
                                 (id, document_id, section_id, clause_path, content,
                                  token_count, page_start, page_end, embedding, metadata)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [
                            (
                                c.id,
                                c.document_id,
                                c.section_id,
                                c.clause_path,
                                c.content,
                                c.token_count,
                                c.page_start,
                                c.page_end,
                                _embedding_literal(c.embedding),
                                _metadata_json(c.metadata),
                            )
                            for c in chunks
                        ],
                    )

    def get_section_tree(self, document_id: UUID) -> list[Section]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, document_id, parent_id, clause_id, title, level, ordinal
                   FROM sections WHERE document_id = %s ORDER BY level, ordinal""",
                (document_id,),
            ).fetchall()
        return [_section_from_row(r) for r in rows]

    def get_chunk(self, chunk_id: UUID) -> Chunk | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, document_id, section_id, clause_path, content,
                          token_count, page_start, page_end, metadata
                   FROM chunks WHERE id = %s""",
                (chunk_id,),
            ).fetchone()
        return _chunk_from_row(row) if row else None

    # --- asks / citations ------------------------------------------------

    def save_ask(self, ask: Ask) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO asks
                     (id, question, status, answer_md, confidence, latency_ms,
                      cost_usd, pipeline_debug, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s, coalesce(%s, now()))""",
                (
                    ask.id,
                    ask.question,
                    ask.status.value,
                    ask.answer_md,
                    ask.confidence,
                    ask.latency_ms,
                    ask.cost_usd,
                    json.dumps(ask.pipeline_debug),
                    ask.created_at,
                ),
            )

    def get_ask(self, ask_id: UUID) -> Ask | None:
        from groundcite.domain.results import AskStatus

        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, question, status, answer_md, confidence, latency_ms,
                          cost_usd, pipeline_debug, created_at
                   FROM asks WHERE id = %s""",
                (ask_id,),
            ).fetchone()
        if not row:
            return None
        return Ask(
            id=row[0],
            question=row[1],
            status=AskStatus(row[2]),
            answer_md=row[3],
            confidence=row[4],
            latency_ms=row[5],
            cost_usd=row[6],
            pipeline_debug=json.loads(row[7]) if row[7] else {},
            created_at=row[8],
        )

    # --- evals (functional stubs; full harness lands Week 3) ------------

    def load_suite(self, suite: str) -> list[EvalCase]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, suite, question, expected_clauses, expected_facts,
                          must_abstain, language
                   FROM eval_cases WHERE suite = %s""",
                (suite,),
            ).fetchall()
        return [
            EvalCase(
                id=r[0],
                suite=r[1],
                question=r[2],
                expected_clauses=tuple(r[3]),
                expected_facts=tuple(r[4]),
                must_abstain=r[5],
                language=r[6],
            )
            for r in rows
        ]

    def save_eval_run(self, run: EvalRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO eval_runs (id, git_sha, config, started_at)
                   VALUES (%s,%s,%s, now())""",
                (run.id, run.git_sha, json.dumps(run.config)),
            )


# --- row mappers ---------------------------------------------------------


def _document_from_row(row) -> Document:
    return Document(
        id=row[0],
        slug=row[1],
        standard_code=row[2],
        title=row[3],
        organization=row[4],
        version=row[5],
        language=row[6],
        source_url=row[7],
        license_note=row[8],
        ingested_at=row[9],
    )


def _section_from_row(row) -> Section:
    return Section(
        id=row[0],
        document_id=row[1],
        parent_id=row[2],
        clause_id=row[3],
        title=row[4],
        level=row[5],
        ordinal=row[6],
    )


def _chunk_from_row(row) -> Chunk:
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


def _embedding_literal(emb) -> str | None:
    if emb is None:
        # The schema's embedding column is NOT NULL; ZeroEmbedder/BgeM3 yields a
        # 1024-d vector. ``None`` here is an upstream bug worth surfacing loudly.
        raise ValueError("Chunk embedding is None — chunks.embedding is NOT NULL.")
    return "[" + ",".join(f"{x:.8f}" for x in emb) + "]"


def _metadata_json(meta: dict[str, object]) -> str:
    return json.dumps(meta or {})


def make_pg_repository(database_url: str) -> PgRepository:
    """Container factory (spec §4 wiring seam)."""
    return PgRepository(database_url=database_url)
