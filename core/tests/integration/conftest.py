"""Integration-test harness: the compose Postgres (CLAUDE rule 3).

These tests exercise the real SQL of the pg_* adapters — the one thing fake
ports cannot cover. They SKIP (not fail) when the DB is unreachable or holds no
ingested corpus, so `uv run pytest` stays green in CI, which runs no database.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from groundcite.config import get_settings


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session", autouse=True)
def _require_db() -> Iterator[None]:
    """Skip EVERY test in this package when the compose Postgres is unreachable.

    autouse, deliberately: a test that forgets to request a DB fixture would
    otherwise sail past the guard and fail in CI (which runs no database) instead
    of skipping — which is exactly what happened the first time this suite ran.
    """
    psycopg = pytest.importorskip("psycopg")
    try:
        with psycopg.connect(_dsn(), connect_timeout=3):
            pass
    except psycopg.Error as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"compose Postgres unreachable: {exc}")
    yield


@pytest.fixture(scope="session")
def ingested_slug() -> Iterator[str]:
    """The slug of a document that is actually ingested, or skip.

    Assertions are written against whatever corpus is present rather than
    hardcoded row counts, so the suite does not rot when the corpus changes.
    """
    import psycopg

    with psycopg.connect(_dsn(), connect_timeout=3) as conn:
        row = conn.execute(
            """SELECT d.slug
                 FROM documents d
                 JOIN chunks c ON c.document_id = d.id
                GROUP BY d.slug
               HAVING count(c.id) > 0
                ORDER BY count(c.id) DESC
                LIMIT 1"""
        ).fetchone()
    if row is None:  # pragma: no cover - environment dependent
        pytest.skip("no ingested document with chunks in the DB")
    yield str(row[0])
