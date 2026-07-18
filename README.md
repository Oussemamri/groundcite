# GroundCite

> **Grounded Q&A over aerospace & engineering standards** — every answer carries
> verifiable clause citations, or the system abstains. Abstention is a feature,
> not a failure.

Open-source hybrid-retrieval infrastructure for regulated engineering domains
(ECSS / EASA CS / FAA FAR / NASA-STD). Engineers waste hours grep-ing
thousand-page PDFs where "clause 5.4.2.1b" must match *exactly*; generic RAG
chatbots hallucinate clause numbers. In a regulated domain a wrong citation is
worse than no answer.

**Status:** Weeks 0–5 done (spec §15) — the full milestone list: ingestion,
hybrid retrieval, the eval harness, generation + abstention gates, an
end-to-end browser demo (`/library`, `/documents/[slug]`, `/evals`) against
a live corpus, and the honest benchmark numbers below. Week 6 (owner-
authorized, spec §15's scope armor reopened for this one feature — see
`docs/ROADMAP.md`) redesigned `/ask` into a multi-turn chat experience
against an owner-supplied design, with real conversation persistence (each
turn still runs its own fully independent pipeline — spec §3.2 unchanged).
See [`GROUNDCITE_PROJECT_SPEC.md`](GROUNDCITE_PROJECT_SPEC.md) — the single
source of truth — and [`CLAUDE.md`](CLAUDE.md) for the coding conventions
that gate every change.

## Non-goals for v1 (scope armor)

- No fine-tuning / training — inference only.
- No accounts/auth (single-tenant, local-first). RBAC is v2.
- No DOORS/ReqIF ingestion (that's Reqlume territory).
- No agentic multi-step tool use. One ask = one pipeline run.
- No Kubernetes — Docker Compose only.
- No scanned-PDF OCR — text-layer PDFs only in v1.

## Architecture (hexagonal — ports & adapters)

```
interfaces  apps/api (FastAPI)   apps/web (Next.js)   cli (Typer)
services    IngestionService  AskService  EvalService  LibraryService
domain      Document  Section  Chunk  Ask  Answer  Citation  ...
ports       EmbeddingProvider  LLMProvider  Reranker  VectorIndex  ...
adapters    bge_m3_embed  groq_llm  pg_vector  pymupdf_parser  ...
```

**Dependency rule (enforced by import-linter in CI):**
`domain ← ports ← services / adapters ← apps`. Core never imports an adapter.
Adding a new vector store or LLM = one adapter file + one config value.

## Quickstart

```bash
# 1. Start Postgres (pgvector, host port 5433) and apply the schema
docker compose up -d db
cd core
uv sync
uv run alembic upgrade head

# 2. Run the quality gates locally (what CI runs)
uv run ruff check .
uv run ruff format --check .
uv run mypy groundcite
uv run lint-imports
uv run pytest
```

Config lives in `core/.env` (copy from [`.env.example`](.env.example)); it is
the single source of environment for every layer, including `apps/api`
(resolved via an absolute path, not the process's CWD).

### Run the demo (API + web)

```bash
# 3. API — FastAPI + SSE, serves /api/v1/* on :8000
cd apps/api
uv sync
uv run uvicorn app.main:app --reload

# 4. Web — Next.js, serves the UI on :3000 (proxies /api/v1/* to the API
#    via next.config.mjs rewrites — no CORS config needed)
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000/ask` and ask a question about an ingested
standard (default demo corpus: 14 CFR Part 25, see below) — the answer
streams token-by-token with live clause citations, or the system abstains
and shows its closest passages instead. Click a citation to jump to the
exact clause in `/documents/[slug]`. `/library` lists ingested standards and
uploads new ones. `/evals` browses every persisted eval run — a per-suite
metric chart plus a per-case drill-down of expected-vs-cited clauses. A
recorded walkthrough of the full loop is in
[`docs/demo/`](docs/demo/) if you'd rather watch than run it.

## Corpus & licensing

PDFs **never** enter git (size + license). `scripts/fetch_corpus.py` downloads
from official sources; `documents.license_note` is mandatory on every ingested
standard. Default demo corpus is **14 CFR Part 25** (US public domain) plus
released NASA standards. See spec §13.

## Benchmarks (spec §8)

Real numbers, straight from [`evals/baseline.json`](evals/baseline.json) (sha
`19de5cd`, τ_retrieval=0.70, `openai/gpt-oss-120b`) — including the
`negative` suite's structural 0.0 recall, not hidden. `/evals` in the running
app renders these same numbers, browsable per-run and per-case.

**Retrieval** (recall@k, MRR — model-independent, unaffected by generation or
τ tuning; identical across every git_sha this project has recorded):

| suite | cases | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| core | 40 | 0.863 | 0.902 | 0.850 |
| german | 10 | 0.917 | 0.958 | 0.938 |
| negative | 10 | 0.0 | 0.0 | 0.0 |

`negative`'s 0.0 is structural, not a failure: every case in that suite is
`must_abstain` with no `expected_clauses`, so there is nothing for recall to
be computed over (`mean([]) == 0.0`) — the suite scores abstention
correctness instead (below), not retrieval.

**Full pipeline** — the honest before/after, including the embarrassing
first number (spec §8: "the blog post narrative is the *improvement*, which
requires committing the bad baseline"). "First baseline" is τ_retrieval=0.35
(the spec default before tuning), sha `695d229`,
[`docs/WEEK3_RESULTS.md`](docs/WEEK3_RESULTS.md) Phase 6. "Current" is
τ_retrieval=0.70, sha `19de5cd`, `evals/baseline.json`:

| suite | abstention acc. (τ=0.35) | abstention acc. (τ=0.70) | citation precision (τ=0.35) | citation precision (τ=0.70) |
|---|---|---|---|---|
| core | 0.975 | 0.900 | 0.846 | 0.885 |
| german | 0.900 | 0.800 | 0.952 | 1.000 |
| negative | 1.000 | 1.000 | — (nothing grounded) | — (nothing grounded) |
| **all 60** | **0.967 (58/60)** | **0.900 (54/60)** | **0.862** | **0.901** |

Recall@5 did **not** move — it's flat at 0.863/0.917 across the whole
tracked history, because τ tuning and the model swap both live entirely
downstream of retrieval; ranking never changed. That's the right number to
report as stable, not a bigger one manufactured for a better-looking table.

**The real improvement is Gate A's leak rate on must-abstain questions**, not
end-to-end abstention accuracy (which reads worse at τ=0.70 by design — see
below). Sweeping candidate τ values against every case's actual recorded
retrieval score:

| τ | must-abstain leak (Gate A alone, before any LLM self-check) |
|---|---|
| 0.35 (spec default) | **25.0%** (3/12) |
| 0.70 (current) | **0.0%** (0/12) — first zero-leak τ |

At τ=0.35, three real must-abstain questions score above threshold on raw
retrieval alone and only avoid a hallucinated answer because the LLM itself
flags `insufficient: true` — a real safety net, but one resting on generation-time
self-honesty rather than the retrieval gate spec §7 designs to catch it. At
τ=0.70, Gate A catches all of them on retrieval score alone, before any LLM
call. The **cost** of that: overall abstention accuracy on already-answerable
questions falls from 0.967 to 0.900 (6 more grounded-eligible cases now
wrongly abstain) — a real, stated trade, not hidden. Full detail:
[`docs/WEEK3_RESULTS.md`](docs/WEEK3_RESULTS.md) Phase 6.

`faithfulness` (LLM-judge, Ragas) is not measured in either baseline — no
second provider key configured — and `/evals` shows this honestly as
unmeasured rather than hiding the column.

## Roadmap

Ingestion, hybrid retrieval, the eval harness, generation + abstention
gates, the `/library` + `/documents/[slug]` web UI, the `/evals` page,
abstention polish, and this README's benchmark table shipped across Weeks
0–5 (spec §15) — see [`docs/WEEK3_RESULTS.md`](docs/WEEK3_RESULTS.md),
[`docs/WEEK4_RESULTS.md`](docs/WEEK4_RESULTS.md), and
[`docs/WEEK5_RESULTS.md`](docs/WEEK5_RESULTS.md) for real numbers and
transcripts. That was the last SPEC-defined feature milestone (spec §15
scope armor: from here forward, bugfixes only unless explicitly reopened by
the owner — new ideas go to [`docs/ROADMAP.md`](docs/ROADMAP.md), not to
code).

**Week 6** ([`docs/WEEK6_RESULTS.md`](docs/WEEK6_RESULTS.md)) is exactly
that kind of owner-authorized exception: `/ask` was redesigned into a
multi-turn chat experience against an owner-supplied design handoff, with
real conversation persistence — verified live against a real 3-turn
conversation (two grounded turns, one real must-abstain question), a cold
reload replaying the full history from Postgres, and a mobile viewport.
Every turn still runs its own fully independent pipeline; nothing in
retrieval, generation, gates, or prompts changed.

A drafted blog post is at [`docs/BLOG_DRAFT.md`](docs/BLOG_DRAFT.md)
(publishing it, making this repo public, and a CV link are owner actions,
not shipped by any commit). The differentiator is a public, reproducible
**eval harness** with real retrieval numbers (recall@k, MRR, citation
precision, faithfulness) that gates every change in CI — including the
honest first baseline, browsable end-to-end on the `/evals` page.

## License

[Apache-2.0](LICENSE).
