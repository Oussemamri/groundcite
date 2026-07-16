# Week 4 — FastAPI + SSE + web `/ask` & documents pages: execution instructions

> Audience: the AI engineer (model) executing Week 4. Read this WHOLE file, then
> `GROUNDCITE_PROJECT_SPEC.md` (§2.2, §7, §9, §10, §11, §12, §15) and
> `CLAUDE.md`, before writing any code. Where this file says "DECIDED", the
> architecture call has already been made with the repo owner — implement it,
> do not re-litigate it.
>
> Deliverable (spec §15 Week 4): **end-to-end demo in the browser — FastAPI +
> SSE serving the full ask pipeline, and the web `/ask`, `/library`, and
> `/documents/[slug]` pages consuming it.** The `/evals` page, README polish,
> demo GIF, and blog post are Week 5 — do not pull them forward.

---

## 0. Non-negotiable rules (violations = rejected work)

1. **Read the spec first** (CLAUDE.md rule 1). If a task here conflicts with
   the spec, stop and say so — except where this file explicitly records a
   spec amendment (spec preamble: when code and spec disagree, fix one of them
   in the same PR).
2. **Dependency rule is law** (rule 2): domain ← ports ← services/adapters ←
   apps. `apps/api` imports services + container — NEVER adapters directly,
   never config internals beyond `get_settings()`/`build_services()`.
   import-linter enforces the 5 core contracts; run before every commit.
3. **Every service-layer change ships with unit tests using fake ports**
   (rule 3). API routes get unit tests via `app.dependency_overrides` with
   stub services (AD-7) — no network, no DB, no model loads. Integration
   tests may use the compose Postgres and MUST auto-skip when unreachable.
4. **Rule 4 (eval run per retrieval/fusion/threshold/prompt change) should not
   trigger this week** — Week 4 adds interface layers only. If you find
   yourself editing chunking, retrieval, fusion, thresholds, or prompts, STOP:
   that is scope creep, and if it is truly unavoidable it carries a full
   before/after eval run per rule 4.
5. **mypy --strict on core; no `Any` in ports** (rule 5). `apps/api` also runs
   mypy (its own config; strict where practical — pydantic/FastAPI decorators
   make full strict cheap here, do it).
6. **TypeScript rules activate this week** (rule 6): TS strict, **no `any`**,
   TanStack Query for ALL server state, SSE types mirror core enums exactly
   (`apps/web/lib/sse.ts` ↔ `domain/results.py` — change both in the same
   commit or neither).
7. **Build-vs-buy** (rule 11 / spec §11.1): SSE plumbing is Buy
   (`sse-starlette` — already on the CLAUDE.md allow-list). Routes, the job
   registry, the SSE reader in the web app, all UI components: Build. NEVER
   add LangChain/LlamaIndex/Haystack, and on the web side the same spirit:
   no component libraries, no axios/swr — Tailwind + fetch + TanStack Query.
   New Python libraries require the spec §11 table row FIRST, same commit
   (Phase 1 does exactly this).
8. **Pin every dependency version** (rule 12) — including `apps/api`
   dependencies (replace the P5 skeleton's `>=` ranges with `==` pins
   verified at build time) and the web lockfile (`package-lock.json` gets
   committed this week — it does not exist yet).
9. **NEVER create or modify anything under `evals/suites/`** (rule 13).
10. **Domain language** (rule 8 / spec §2.1): Ask, Citation, Abstention,
    Suite/Case/Run, GROUNDED/ABSTAINED — in API paths, response models, UI
    copy, and TS types. §2.2 copy rules: abstention card title is exactly
    "No grounded answer", never joke in abstentions.
11. **Small diffs, one feature per commit, conventional commits** (rule 7).
    Secrets only via config (rule 9); the web app gets NO secrets at all —
    it talks only to the API.

**Working style** (rule 0): diagnose with evidence before coding; failing test
first for every fix; boring beats clever; surgical diffs; state assumptions.

---

## 1. Where the project stands (verified facts, 2026-07-16)

Weeks 0–3 are done and pushed; CI is green on `main` (sha `bf7937d`).

**Working today (core, all behind `groundcite` CLI):**
- Ingestion: FAR-25 ingested — 3,291 sections, 1,573 chunks, bge-m3 1024-d.
- Full ask pipeline: `AskService.ask(question, document_slugs) ->
  Iterator[AskEvent]` — retrieval → rerank → Gate A (τ=0.70, reranker
  REQUIRED, spec §7.1 amendment) → streamed generation (Groq
  `openai/gpt-oss-120b`) → parse+repair → Gate B → persist → FINAL/ERROR.
  Event order contract: STAGE… TOKEN… CITATIONS, exactly one terminal event.
  **`AskEvent` is already SSE-shaped — the API must NOT invent a second event
  type** (spec §7: API and web share one enum).
- Evals: retrieval-only + full-pipeline runners, persisted (eval_runs /
  eval_results with upserted eval_cases), `groundcite eval report <run-id>`.
- Baseline: `evals/baseline.json` + `scripts/check_baseline.py` (manual gate).

**Measured Week 3 final numbers (sha `19de5cd`, τ=0.70, gpt-oss-120b):**

| suite | grounded | abstained | abstention accuracy | mean citation precision |
|---|---|---|---|---|
| core (40) | 36 | 4 | 0.900 | 0.885 |
| german (10) | 6 | 4 | 0.800 | 1.000 |
| negative (10) | 0 | 10 | 1.000 | — |

Zero must-abstain cases answered GROUNDED, all week, every run. Retrieval:
core 0.863/0.902/0.850 (r@5/r@10/MRR) — identical to Week 2 final.

**The P5 skeleton you are building on (verified in code, not guessed):**
- `apps/api/app/`: `main.py` (`create_app()`, only `/healthz` wired),
  `deps.py` (`get_services()` — **calls `build_services()` per call: this
  reloads the reranker per request and MUST become a singleton, AD-1**),
  `sse.py` (`format_sse()` re-exporting core `AskEvent` — correct instinct,
  superseded by sse-starlette in AD-2), `routes/health.py` (static ok).
  `pyproject.toml` declares `groundcite` as an editable path dep — **no venv
  exists yet; `uv sync` has never been run in `apps/api`.**
- `apps/web/`: Next.js 15 skeleton, all four pages exist as shells
  (`ask/`, `library/`, `documents/[slug]/`, `evals/`), `layout.tsx` with
  Inter + JetBrains Mono wired, `providers.tsx` with TanStack QueryClient,
  `tailwind.config.ts` with the FULL §2.2 mission-control palette already
  tokenized (background/surface/border/text/grounded/abstained/link),
  `lib/sse.ts` with the typed event enum + a single-frame parser (the
  streaming reader is explicitly deferred to this week). **`npm install` has
  never been run — no `node_modules`, no lockfile.**
- Node v24.15.0 + npm 11.12.1 are installed and on PATH.

**Repository port reads that exist:** `get_document(slug)`,
`list_documents()`, `get_section_tree(document_id)`, `get_chunk(chunk_id)`,
`get_ask(ask_id)`, `get_eval_run(run_id)`, `get_eval_results(run_id)`.

**Reads that DO NOT exist (you add them, AD-4):**
- citations for an ask (`asks` row has no citations; `citations` table has no
  reader) — needed by `GET /asks/{id}` replay.
- `list_eval_runs()` — needed by `GET /eval/runs`.
- chunks of a document (ordered, for the reader page) — `get_chunk` is
  by-id only.
- `LibraryService` is an EMPTY class — implement it this week (it exists so
  the API depends on a service, not on Repository directly).

**Week 3 residuals this file disposes of (from `docs/WEEK3_RESULTS.md`):**
1. gpt-oss-120b parse-failure (1/62 calls, caught safely) → WATCH only; if
   seen again during Week 4 smoke runs, record frequency in
   WEEK4_RESULTS.md — do not fix speculatively.
2. 3-way model eval-off → NOT this week (quota + out of scope; stays in the
   backlog, needs an owner decision to spend on it).
3. CI has no Postgres/corpus → DECIDED this week, AD-8 (service container:
   yes; baseline eval in CI: still no, reason stated there).
4. Local `.env` config-drift class of bug → cheap hardening lands here:
   Phase 2 adds `tau_retrieval` + `groq_model` to `/healthz`'s payload, so
   drift is visible from one request (they are already persisted in every
   eval run's config since `c9a45fb`).

---

## 2. Look-outside survey (done — verdicts binding per rule 11)

| Candidate | Verdict | Why |
|---|---|---|
| **`sse-starlette`** | **ADOPT** (pinned, apps/api dep) | Already on the CLAUDE.md allow-list; spec §11.1 puts SSE plumbing under Buy. `EventSourceResponse` handles headers, ping/keep-alive, and client-disconnect; it accepts a **sync** iterator (starlette iterates it in a threadpool — exactly what the blocking `ask()` generator needs, AD-2). |
| **`structlog`** | **ADOPT** (pinned, apps/api dep) | Named explicitly in spec §12. API-layer only — core stays logging-free. JSON logs, `ask_id` bound per request. |
| **`python-multipart`** | **ADOPT** (pinned, apps/api dep) | FastAPI hard-requires it for multipart uploads (`POST /documents`, spec §9). |
| **`httpx`** | **ADOPT** (pinned, apps/api DEV dep only) | Starlette's `TestClient` requires it. Test-only; not a runtime dep. |
| `celery` / `rq` / `arq` / `dramatiq` | reject | Spec §9 says "BackgroundTask in v1" verbatim. A queue is v2 infrastructure with no v1 requirement (AD-5). |
| `fastapi-problem` / `rfc7807` helpers | reject | RFC-7807 is ~20 lines of exception handler (AD-6). Build. |
| WebSockets | reject | Spec §7/§9/§10 say SSE. One-directional stream; SSE is the simpler, correct tool. |
| CORS middleware | reject (avoid the problem) | Next.js rewrites proxy `/api/v1/*` to the API in dev — same-origin, zero CORS config, prod-shaped (AD-3). |
| `axios` / `swr` / `ky` (web) | reject | Rule 6: TanStack Query + native `fetch`. The SSE reader is `fetch` + `ReadableStream` per spec §10. |
| shadcn/ui, Radix, MUI, etc. | reject | §2.2 theme is hand-tokenized already; v1 UI is a few components (chip, cards, tree). Component libs dilute the portfolio piece and fight the theme. |
| `eventsource-parser` (npm) | reject | `lib/sse.ts` frame parser exists and is ~20 lines; finishing the reader is Build (spec §10 names `fetch` + ReadableStream explicitly). |
| `recharts` | defer | Spec §10 names it — for `/evals` (Week 5). Do not add this week. |

**Version rule (spec §11 last row):** verify current versions of
fastapi / uvicorn / sse-starlette / structlog / python-multipart / httpx at
build time and pin exact (`==`). Same for the npm lockfile — commit it.

---

## 3. Architecture decisions (DECIDED — implement, don't re-litigate)

**AD-1 — Services are a process-wide singleton via FastAPI lifespan.**
`build_services(get_settings())` runs ONCE in the app's lifespan startup and
is stored on `app.state.services`; `deps.get_services` returns it. Rationale:
the reranker/embedder adapters lazy-load ~2GB of models — per-request
construction (the current P5 `deps.py`) would reload them per call. The
existing lazy-loading means startup stays fast; first ask pays the model
load. Single-tenant v1: one shared instance is correct; do not add pooling.

**AD-2 — `POST /api/v1/asks` streams via sse-starlette over the SYNC
generator.** The route body: parse request → `services.ask.ask(question,
document_slugs)` → wrap each `AskEvent` as a `ServerSentEvent(event=
event.type.value, data=json.dumps(event.data))` → `EventSourceResponse`.
The core generator is synchronous and blocking (reranker CPU + LLM network)
— sse-starlette/starlette iterate sync iterators in a threadpool, so the
event loop is never blocked. VERIFY this at build time with two concurrent
asks + a concurrent `/healthz` (must respond instantly). Event names and
payloads come from core `AskEvent` — the existing `apps/web/lib/sse.ts`
enum already matches; do not invent a second event vocabulary. Client
disconnect must terminate the generator (sse-starlette handles this; verify
with a killed `curl`, then check the API log shows the stream closed —
the ask row still persists: persistence happens inside `ask()` before FINAL).

**AD-3 — Web→API integration via Next.js rewrites, not CORS.**
`next.config.mjs` gains `rewrites()`: `/api/v1/:path*` →
`http://localhost:8000/api/v1/:path*` (API base URL from env
`API_ORIGIN`, default localhost:8000). The browser only ever talks
same-origin; no CORS middleware, no preflight, and the SSE stream proxies
fine through Next dev. This is also the prod shape (reverse proxy).

**AD-4 — Repository port read extensions (port + `pg_repo` + `FakeRepository`
in lockstep, one commit):**
- `get_ask_citations(ask_id: UUID) -> list[Citation]` — ordered by rank;
  powers `GET /asks/{id}` replay (spec §9: "answer + citations + debug").
- `list_eval_runs() -> list[EvalRun]` — newest first; powers `GET /eval/runs`.
- `list_chunks(document_id: UUID) -> list[Chunk]` — ordered by clause_path;
  powers the reader page. 1,573 chunks for far-25 renders acceptably in v1;
  note it as a residual if it feels slow, do not paginate speculatively.
`LibraryService` gets the real implementation: `list_documents()`,
`get_document(slug)` (+ section tree + chunks). Unit tests with FakeRepository
first (rule 3).

**AD-5 — Long-running POSTs use FastAPI `BackgroundTasks` + an in-memory job
registry.** `POST /documents` (multipart PDF + metadata → `{job_id}`, spec §9
verbatim) and `POST /eval/runs` (body `{suite, full: bool}` → `{job_id}`)
both: create a job record (`app.state.jobs: dict[UUID, Job]` — id, kind,
status queued|running|done|error, detail, created_at), schedule the service
call as a BackgroundTask, return 202 + job_id. `GET /jobs/{job_id}` reads
status. In-memory is a DECIDED v1 trade: single-tenant, and a process restart
loses only job STATUS — the underlying work persists in Postgres (documents /
eval_runs). Say this in the module docstring. Do NOT add a jobs table or a
queue. Uploaded PDFs go to a temp dir via `tempfile` — never into the repo.

**AD-6 — API contract discipline.** Response models are pydantic models in
`apps/api/app/models.py`, mapped EXPLICITLY from domain objects — never
`model_dump()` a domain entity into a response (spec §9: "pydantic response
models shared nowhere with domain entities"). Errors are RFC-7807
`application/problem+json` via exception handlers: 404 (unknown slug/id),
422 (validation — remap FastAPI's default), 409 (e.g. ingest slug conflict),
503 (`/healthz` failures), 500 (fallback, no stack traces in the body).
`type` URIs use `https://groundcite.dev/problems/<slug>` (they don't need to
resolve; they need to be stable).

**AD-7 — API tests: unit-first via `app.dependency_overrides`.**
`apps/api/tests/` defines a tiny `StubServices` (only the methods routes
touch; core's `tests/fakes.py` is not installed with the package — do NOT
import it, duplicate the 3 stubs you need at the `Services` seam instead).
Unit-test per route: happy path, RFC-7807 shape on 404, SSE event ORDER on a
scripted 3-event stream, job lifecycle (202 → running → done). One
integration test module (auto-skip without DB, same guard pattern as core)
drives `TestClient` against real services with the live Postgres:
`GET /documents` (far-25 present), `GET /documents/far-25` (tree non-empty),
`GET /chunks/{real-id}`. The full live SSE ask is a MANUAL smoke with a
pasted transcript (it spends Groq tokens; keep it out of pytest).

**AD-8 — CI expansion (disposes of the Week-3 deferral).** Three changes:
1. Core job gains a `postgres: pgvector/pgvector:pg16` service container →
   the existing integration tests STOP auto-skipping in CI (they create
   their own schema/fixtures; verify locally with a scratch DB first).
2. New `api` job: `uv sync` in `apps/api`, ruff, mypy, pytest (unit only —
   no DB needed thanks to AD-7's stubs; integration tests auto-skip).
3. New `web` job: `npm ci`, `tsc --noEmit`, `next lint`, `next build`.
**Still NOT in CI, explicitly:** `scripts/check_baseline.py` and any
real-embedding eval — they need the 2GB bge models + a 35-min corpus ingest;
that cost/flake budget is wrong for per-commit CI. They remain the manual
rule-4 gate. State exactly this in the commit message.

**AD-9 — Observability (spec §12).** structlog JSON to stdout in the API
layer only. Middleware binds a request id; the asks route binds `ask_id` as
soon as the FINAL/ERROR event carries it (log line per stage transition, not
per token). `/healthz` extends to: DB (`SELECT 1` via the repository),
provider (Groq `GET /models` — free, no token spend), plus the running
config's `tau_retrieval` and `groq_model` (residual #4 hardening). Any check
failing → 503 problem+json with per-check detail.

**AD-10 — Web implementation contract.** All server state through TanStack
Query (`useQuery` for documents/document/chunk/jobs, no manual `useEffect`
fetching). The ask stream is NOT TanStack state — it's a `ReadableStream`
consumed by a hand-rolled hook (`useAskStream`) that finishes `lib/sse.ts`:
`fetch('/api/v1/asks', {method: 'POST', body: …})` → `res.body.getReader()`
→ TextDecoder → frame-split on `\n\n` → existing `parseSseFrame` → typed
state machine (stage → tokens accumulate → citations → final|error).
Components (Build, plain Tailwind): `StatusChip` (GROUNDED green / ABSTAINED
amber + confidence, §2.2), `CitationCard` (mono clause_path, snippet, score;
click → `/documents/[slug]?chunk=<id>`), `AbstentionCard` (exact §2.2 copy:
title "No grounded answer", subtitle "Confidence below threshold — closest
passages shown below.", renders top_passages — an abstention is a first-class
result, not an error state), `ClauseTree` (recursive, expand/collapse,
current-chunk highlight). Every clause ID, standard code, and score renders
in `font-mono` — the §2.2 signature detail; audit for this before the demo.

---

## 4. Phase plan (execute in order; every step has a verify line)

### Phase 0 — Orientation + environment (no feature code)
1. Read spec §2.2, §7, §9, §10, §11, §12 + CLAUDE.md + this file. Read
   `apps/api/app/*.py` (all four files — they encode intent), `apps/web/`
   (layout, providers, tailwind config, lib/sse.ts, the four page shells),
   `core/groundcite/container.py`, `services/library.py`,
   `ports/protocols.py` (Repository), `domain/results.py` (AskEvent shape).
2. Environment bring-up: `uv sync` in `apps/api` (creates its venv; core
   resolves as editable path dep); `npm install` in `apps/web` (FIRST ever —
   commit `package-lock.json` in the Phase 6 commit); `npm run dev` renders
   the shell pages; `uvicorn app.main:app --reload` serves `/healthz`.
3. **OWNER GATE — one question, default already chosen:** judge metrics
   (faithfulness via ragas) need a second LLM provider key (judge ≠
   answerer, spec §8). DEFAULT: still skipped — Week 4 has no judge
   requirement. Only if the owner volunteers an OpenAI key this week does
   the eval-run route pass `judge=True` through; build nothing speculative.
   → **verify:** both dev servers up simultaneously; `/healthz` 200; shell
   pages render with the dark theme; no code changes yet.

### Phase 1 — Core read extensions (the only core work this week)
4. AD-4: extend Repository port + `pg_repo` + `FakeRepository`; implement
   `LibraryService`; unit tests with fakes (rule 3): tree shape (parents
   before children, ordering), citations ordered by rank, empty-library and
   unknown-slug behaviors (None, not raise).
5. Integration check against live far-25 DB: `list_documents()` returns 1,
   `get_section_tree` returns 3,291, `list_chunks` 1,573 ordered.
   → **verify:** ruff, mypy --strict (both install states — hide/restore
   optional extras exactly like Week 3), import-linter 5/5, full pytest.
   ONE commit: `feat(core): library reads + ask-citations read (Week 4 AD-4)`.

### Phase 2 — API foundation + read routes
6. Spec §11 table rows + pinned deps (`sse-starlette`, `structlog`,
   `python-multipart`; `httpx` dev) — same commit as first use (rule 11).
7. AD-1 lifespan singleton (fix `deps.py`); AD-6 RFC-7807 handlers + response
   models; AD-9 structlog middleware + extended `/healthz`.
8. Read routes under `/api/v1`: `GET /documents`, `GET /documents/{slug}`
   (doc + section tree; `?include=chunks` for the reader), `GET /chunks/{id}`,
   `GET /asks/{id}` (answer + citations + pipeline_debug), `GET /eval/runs`,
   `GET /eval/runs/{id}` (run + per-case results).
   → **verify (AD-7):** unit tests green with stubs; RFC-7807 asserted on
   404s; integration module green against live DB; `curl` transcripts for
   two routes pasted in the commit message.

### Phase 3 — The SSE ask route (the heart of the week)
9. AD-2: `POST /api/v1/asks` body `{question, document_slugs?}` →
   EventSourceResponse. Include the `ask_id` in the FINAL event payload
   (it is already in `ask()`'s FINAL data — do not duplicate).
10. Concurrency + disconnect verification (AD-2's two explicit checks).
    → **verify:** unit test asserts event ORDER + terminal-event uniqueness
    through the route (scripted stub stream); MANUAL live smoke: one real
    `curl -N` SSE transcript (grounded) + one abstention transcript pasted
    into the commit message; `/healthz` under 100ms while an ask streams.

### Phase 4 — Write routes: ingestion upload + eval trigger + jobs
11. AD-5: `POST /documents` (multipart), `POST /eval/runs`, `GET /jobs/{id}`.
    Ingestion BackgroundTask calls `services.ingestion.ingest()` with the
    temp-file path and the metadata fields (slug, code, org, title…).
    → **verify:** unit: job lifecycle with a stubbed slow service (queued →
    running → done; error path sets status=error + detail). MANUAL: re-upload
    far-25 is NOT run (35-min ingest, corpus frozen); instead upload the
    smallest corpus PDF available with a `--slug demo-tmp`… if none is small,
    verify the 202/job path with a deliberately-invalid PDF (fast failure →
    status=error) and say so honestly in the commit.

### Phase 5 — CI expansion (AD-8)
12. Postgres service container for the core job; new `api` and `web` jobs.
    → **verify:** push on a branch first if unsure; CI green with the core
    integration tests actually EXECUTING (check the job log shows them run,
    not skipped — that's the whole point). Commit message states what is
    still manual and why (AD-8 wording).

### Phase 6 — Web foundation
13. Commit the lockfile; finish `lib/sse.ts` streaming reader + `useAskStream`
    hook (AD-10); typed API client (`lib/api.ts`: thin fetch wrappers
    returning the TS mirror types); AD-3 rewrites; shared nav in `layout.tsx`
    (Ask / Library / Evals links; Evals page stays a labeled Week-5 stub).
    → **verify:** `tsc --noEmit` clean (strict, no `any` — grep the diff),
    `next lint` clean, `next build` clean.

### Phase 7 — `/ask` page
14. AD-10 components + page assembly: input → stream → tokens render live →
    citations panel fills → StatusChip + confidence; AbstentionCard renders
    top_passages on ABSTAINED; error event → calm §2.2-tone error, never a
    blank screen.
    → **verify:** BROWSER demo — one grounded ask (citations clickable) and
    one abstention, screenshots (or short capture) referenced in the commit;
    mono-font audit on clause IDs/scores.

### Phase 8 — `/library` + `/documents/[slug]` reader
15. `/library`: documents table (org, code, version, chunks count,
    license_note — spec §10) + upload form → job progress via
    `GET /jobs/{id}` polling (TanStack `refetchInterval` while running).
16. Reader: left `ClauseTree`, right ordered chunk content; `?chunk=<id>`
    deep-link scrolls to + highlights the chunk (this is where CitationCard
    clicks land — the citation-resolution loop closes here).
    → **verify:** click a citation on `/ask` → correct clause highlighted in
    the reader; deep-link URL works cold (paste into a fresh tab).

### Phase 9 — End-to-end demo + close-out
17. The spec §15 proof: full browser flow — ask → streamed grounded answer →
    click citation → reader highlight; plus one abstention. Capture it.
18. Full gates everywhere: core (ruff/mypy both states/import-linter/pytest),
    api (ruff/mypy/pytest), web (tsc/lint/build). Push; CI green (now 3 jobs).
19. Write `docs/WEEK4_RESULTS.md` (same honesty pattern as Week 3): what
    shipped, transcripts/screenshots, decisions taken (ADs that changed
    during execution, with why), residuals for Week 5.
    → **verify:** README quick-start still true (update the run commands if
    they changed); WEEK4_RESULTS.md committed; CI green on final sha.

---

## 5. Explicitly OUT of scope (do not touch)

- `/evals` page, recharts, README polish, demo GIF, blog post (Week 5).
- Judge metrics unless the owner volunteers a second provider key (Phase 0).
- Any retrieval/fusion/threshold/prompt change (rule 4 armor — see §0.4).
- Corpus changes, re-ingestion of far-25, `evals/suites/*` (rule 13).
- Auth, multi-tenancy, rate limiting, k8s, docker images for api/web
  (compose stays Postgres-only in v1; api/web run as dev servers — the spec
  §4.1 compose note is aspirational, not a Week-4 deliverable).
- Queue infrastructure (AD-5 decided BackgroundTasks).
- Qdrant, `tsv_de`, MCP server (§16 extensions).
- The 3-way model eval-off (backlog; owner decision on quota spend).

## 6. Environment facts (save yourself the rediscovery)

- Windows 11; PowerShell 5.1 primary (no `&&`; beware `2>&1` on native exes);
  Git Bash available and preferred for long/detached runs.
- Core venv: `core\.venv\Scripts\python.exe`; api venv will be
  `apps\api\.venv\...` after Phase 0's `uv sync`. Node v24.15.0, npm 11.12.1.
- Ports: web 3000, api 8000, Postgres **5433** (container `groundcite-db`).
  Docker Desktop dies with laptop sleep/power events — restart it and wait
  for `(healthy)` before blaming your code. The pg data volume survives.
- Groq: model `openai/gpt-oss-120b`, free-tier quota 200K tokens/day —
  measured ~3K tokens/full-pipeline ask. Budget manual SSE smokes
  accordingly; never put a live-LLM call in pytest.
- `core/.env` is the live config (gitignored). After the Week-3 incident:
  if a number surprises you, check `get_settings()` output FIRST —
  `/healthz` exposes the two that matter after Phase 2.
- Long-running work (ingest ~35 min, full evals): detached
  (`nohup … & disown` in Git Bash), log to a file, monitor the file — never
  block a session on it, and expect the PC to power off overnight.
- mypy CI-parity ritual for core changes: hide/restore
  `openai`/`FlagEmbedding`/`rerankers` site-packages dirs + `--no-incremental`
  (Week 3's proven pattern — copy it, don't rediscover it).

## 7. Evidence bar (how your work gets accepted)

Every commit that changes behavior carries, in its message: the command(s)
run and their real output — `curl` transcripts for API routes (including one
full SSE frame sequence), test-suite tails, and for the web phases
screenshots or a capture of the actual browser. The Week-4 deliverable is a
demo; a demo that was never actually demonstrated does not merge. When
something is worse than expected (slow reader render, ugly stream jitter,
a flaky disconnect), the honest number/observation goes in
`docs/WEEK4_RESULTS.md` — Week 3's detours are the precedent: the bad number
IS the story.
