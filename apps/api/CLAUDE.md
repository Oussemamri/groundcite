# `apps/api/` — FastAPI + SSE (interface layer over `core`)

Supplements the root [`CLAUDE.md`](../../CLAUDE.md) and
[`GROUNDCITE_PROJECT_SPEC.md`](../../GROUNDCITE_PROJECT_SPEC.md) — read those
first; this file only adds what's specific to working inside `apps/api/`.

## Gate commands (run before every commit that touches this directory)

```bash
cd apps/api
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests        # ALWAYS together — see gotcha below
uv run pytest -q
```

venv: `apps/api/.venv/Scripts/python.exe` (Windows). `uv sync` creates it;
`groundcite` resolves as an editable path dependency on `../../core`.

**Gotcha, found twice already:** `mypy app` alone does not check `tests/`,
and real type errors have hidden there before (an untyped fixture param, a
generically-typed `dependency_overrides` call, a stale `# type: ignore`).
Always run `mypy app tests` together — that IS the correct invocation, not a
slower/optional extra one.

## Rules specific to this directory

- **Dependency extras matter.** `pyproject.toml` must depend on
  `groundcite[embed,rerank,llm,pdf]`, never bare `groundcite` — a live route
  that touches the reranker, the LLM, or ingestion will fail at runtime with a
  confusing "X is not installed" error if an extra is missing, and no stub
  test catches it (only a real request does). If you add a route that
  exercises a new part of core, check its extras are present, then verify
  with a real live request, not just green stub tests.
- **Config resolves from `core/.env` via an absolute path**, not the
  process's CWD (`config.py`'s `_REPO_ROOT`-anchored `env_file`). This was a
  real, hard-to-diagnose bug once (silently fell back to defaults, including
  a missing API key, with no clean error). Don't reintroduce a
  CWD-relative path anywhere in this app.
- **Services + jobs are process-wide singletons**, built once in
  `main.py`'s `lifespan` and stored on `app.state.services` /
  `app.state.jobs` (AD-1, AD-5). Never rebuild `Services` per-request — the
  reranker/embedder lazy-load real models; per-request construction reloads
  them on every call. If a test needs `app.state.jobs`, set a real
  `JobRegistry()` in the fixture (it's free, in-memory) — don't stub it.
- **Response models are explicit, never `model_dump()` on a domain
  entity** (AD-6). Every `*Out` model in `app/models.py` has a
  `from_domain`/`from_job` classmethod that names each field. This is spec
  §9's contract ("pydantic response models shared nowhere with domain
  entities") and it's also what keeps a domain-internal field (like a raw
  embedding vector) from ever leaking into an HTTP response by accident.
- **Errors are RFC-7807 `application/problem+json`** via the exception
  handlers in `app/errors.py` — a new failure mode gets a `NotFoundError` (or
  a new typed exception + handler), never an ad-hoc `HTTPException` with a
  bare string body.
- **SSE routes wrap `sse-starlette`'s `EventSourceResponse` over the
  existing SYNC `AskService.ask()` generator** (AD-2) — don't build a second
  event vocabulary; `AskEvent` from `core` is already SSE-shaped and
  `apps/web/lib/sse.ts` mirrors it exactly. If you touch this, verify live
  (a real `curl -N` transcript) that a concurrent `/healthz` still answers
  fast while a stream is in flight — that's the whole point of the sync
  generator + threadpool design, and it can silently regress.
- **Unit tests use `app.dependency_overrides` with stub services**
  (`tests/conftest.py`'s `StubServices`/`StubAsk`/`StubEvals`/`StubIngestion`)
  — no network, no DB, no model loads (root rule 3). One integration module
  per resource drives `TestClient` against real services + live Postgres,
  auto-skipping when the DB is unreachable (`_require_db`-style fixture — copy
  the existing pattern). A full live SSE ask that spends real LLM tokens is a
  **manual smoke**, never a pytest case.
