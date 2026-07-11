"""Initial schema (spec §5) — full data model, verbatim.

Revision ID: 0001
Revises:
Create Date: 2026-07-11

The ``_SCHEMA_SQL`` below is copied verbatim from GROUNDCITE_PROJECT_SPEC.md §5.
If code and spec disagree, fix one of them in the same PR (spec preamble).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- Verbatim schema from spec §5 ------------------------------------------
_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text UNIQUE NOT NULL,          -- 'far-25', 'ecss-e-st-40c'
  standard_code text NOT NULL,                 -- '14 CFR Part 25'
  title         text NOT NULL,
  organization  text NOT NULL,                 -- 'FAA', 'ESA', 'NASA'
  version       text,
  language      text NOT NULL DEFAULT 'en',
  source_url    text,
  license_note  text NOT NULL,                 -- redistribution status, ALWAYS filled
  ingested_at   timestamptz
);

CREATE TABLE sections (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents ON DELETE CASCADE,
  parent_id   uuid REFERENCES sections,
  clause_id   text NOT NULL,                   -- '5.4.2.1' or '25.1309'
  title       text,
  level       int  NOT NULL,
  ordinal     int  NOT NULL,                   -- order within parent
  UNIQUE (document_id, clause_id)
);

CREATE TABLE chunks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id  uuid NOT NULL REFERENCES documents ON DELETE CASCADE,
  section_id   uuid NOT NULL REFERENCES sections ON DELETE CASCADE,
  clause_path  text NOT NULL,                  -- 'ECSS-E-ST-40C §5.4.2.1'
  content      text NOT NULL,                  -- includes breadcrumb header (see §6)
  token_count  int NOT NULL,
  page_start   int, page_end int,
  embedding    vector(1024) NOT NULL,
  tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  metadata     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX chunks_clause_idx    ON chunks (document_id, clause_path);

CREATE TABLE asks (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  question       text NOT NULL,
  status         text NOT NULL,                -- 'grounded' | 'abstained' | 'error'
  answer_md      text,
  confidence     real,
  latency_ms     int,
  cost_usd       numeric(8,5),
  pipeline_debug jsonb NOT NULL,               -- per-stage timings, candidates, scores
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE citations (
  ask_id   uuid REFERENCES asks ON DELETE CASCADE,
  chunk_id uuid REFERENCES chunks,
  rank     int NOT NULL,
  score    real NOT NULL,
  PRIMARY KEY (ask_id, chunk_id)
);

-- Evals
CREATE TABLE eval_cases (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suite            text NOT NULL,
  question         text NOT NULL,
  expected_clauses text[] NOT NULL,            -- clause_paths that MUST be retrieved
  expected_facts   text[] NOT NULL DEFAULT '{}',
  must_abstain     boolean NOT NULL DEFAULT false,
  language         text NOT NULL DEFAULT 'en'
);
CREATE TABLE eval_runs (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  git_sha    text NOT NULL,
  config     jsonb NOT NULL,                   -- full retrieval/model config snapshot
  started_at timestamptz DEFAULT now(),
  finished_at timestamptz
);
CREATE TABLE eval_results (
  run_id             uuid REFERENCES eval_runs ON DELETE CASCADE,
  case_id            uuid REFERENCES eval_cases,
  recall_at_5        real, recall_at_10 real, mrr real,
  citation_precision real, faithfulness real,
  abstained          boolean, passed boolean NOT NULL,
  debug              jsonb NOT NULL,
  PRIMARY KEY (run_id, case_id)
);
"""

# Reverse order for a clean teardown (children before parents).
_DROP_SQL = """
DROP TABLE IF EXISTS eval_results;
DROP TABLE IF EXISTS eval_runs;
DROP TABLE IF EXISTS eval_cases;
DROP TABLE IF EXISTS citations;
DROP TABLE IF EXISTS asks;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS sections;
DROP TABLE IF EXISTS documents;
DROP EXTENSION IF EXISTS vector;
"""


def _run(sql: str) -> None:
    bind = op.get_bind()
    for statement in (s.strip() for s in sql.split(";")):
        if statement:
            bind.exec_driver_sql(statement)


def upgrade() -> None:
    _run(_SCHEMA_SQL)


def downgrade() -> None:
    _run(_DROP_SQL)
