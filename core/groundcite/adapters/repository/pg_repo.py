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
from groundcite.domain.results import AskStatus, Citation, EvalResult, EvalRun


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

    # --- asks / citations (one transaction, AD-6) --------------------------------

    def save_ask(self, ask: Ask, citations: Sequence[Citation]) -> None:
        # One transaction writing the ask row + its citation rows (rank, score
        # from the final context ranking, AD-6). An abstention has no citations.
        with self._connect() as conn, conn.transaction():
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
            if citations:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO citations (ask_id, chunk_id, rank, score)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (ask_id, chunk_id) DO UPDATE
                              SET rank = EXCLUDED.rank, score = EXCLUDED.score""",
                        [(ask.id, c.chunk_id, c.rank, c.score) for c in citations],
                    )

    def get_ask(self, ask_id: UUID) -> Ask | None:
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
            pipeline_debug=row[7] or {},  # psycopg3 auto-deserializes jsonb to dict
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

    def save_eval_run(
        self, run: EvalRun, cases: Sequence[EvalCase], results: Sequence[EvalResult]
    ) -> None:
        # One transaction (AD-6): upsert the Cases (they live in JSONL, rule 13 —
        # not the DB — so eval_results.case_id's FK has nothing to point at until
        # this runs), then the run row, then all its per-Case result rows.
        # started_at/finished_at both stamp `now()` — runs are synchronous
        # (spec §8 Phase 5: "per case run ask(), non-streamed collection"), so
        # there is no separate start-then-finish phase to track a real duration.
        with self._connect() as conn, conn.transaction():
            if cases:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO eval_cases
                             (id, suite, question, expected_clauses, expected_facts,
                              must_abstain, language)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (id) DO UPDATE SET
                             question          = EXCLUDED.question,
                             expected_clauses  = EXCLUDED.expected_clauses,
                             expected_facts    = EXCLUDED.expected_facts,
                             must_abstain      = EXCLUDED.must_abstain,
                             language          = EXCLUDED.language""",
                        [
                            (
                                c.id,
                                c.suite,
                                c.question,
                                list(c.expected_clauses),
                                list(c.expected_facts),
                                c.must_abstain,
                                c.language,
                            )
                            for c in cases
                        ],
                    )
            conn.execute(
                """INSERT INTO eval_runs (id, git_sha, config, started_at, finished_at)
                   VALUES (%s,%s,%s, now(), now())""",
                (run.id, run.git_sha, json.dumps(run.config)),
            )
            if results:
                with conn.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO eval_results
                             (run_id, case_id, recall_at_5, recall_at_10, mrr,
                              citation_precision, faithfulness, abstained, passed, debug)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        [
                            (
                                r.run_id,
                                r.case_id,
                                r.recall_at_5,
                                r.recall_at_10,
                                r.mrr,
                                r.citation_precision,
                                r.faithfulness,
                                r.abstained,
                                r.passed,
                                json.dumps(r.debug),
                            )
                            for r in results
                        ],
                    )

    def get_eval_run(self, run_id: UUID) -> EvalRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, git_sha, config FROM eval_runs WHERE id = %s",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return EvalRun(id=row[0], git_sha=row[1], config=row[2] or {})

    def get_eval_results(self, run_id: UUID) -> list[EvalResult]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT run_id, case_id, recall_at_5, recall_at_10, mrr,
                          citation_precision, faithfulness, abstained, passed, debug
                   FROM eval_results WHERE run_id = %s""",
                (run_id,),
            ).fetchall()
        return [
            EvalResult(
                run_id=r[0],
                case_id=r[1],
                recall_at_5=r[2],
                recall_at_10=r[3],
                mrr=r[4],
                citation_precision=r[5],
                faithfulness=r[6],
                abstained=r[7],
                passed=r[8],
                debug=r[9] or {},
            )
            for r in rows
        ]


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
        metadata=row[8] or {},  # psycopg3 auto-deserializes jsonb to dict
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
