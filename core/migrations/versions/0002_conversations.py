"""Conversations (spec §5, Week 6) — group already-independent Asks for the
`/ask` chat UI. NOT a new generation capability: no prior-turn context is
ever passed to the LLM, spec §3.2's "one ask = one pipeline run" non-goal is
unchanged. Copied verbatim from GROUNDCITE_PROJECT_SPEC.md §5.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SCHEMA_SQL = """
CREATE TABLE conversations (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title      text NOT NULL,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE asks ADD COLUMN conversation_id uuid REFERENCES conversations ON DELETE CASCADE;
CREATE INDEX asks_conversation_idx ON asks (conversation_id, created_at);
"""

_DROP_SQL = """
DROP INDEX IF EXISTS asks_conversation_idx;
ALTER TABLE asks DROP COLUMN IF EXISTS conversation_id;
DROP TABLE IF EXISTS conversations;
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
