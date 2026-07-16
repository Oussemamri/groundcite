# GroundCite

> **Grounded Q&A over aerospace & engineering standards** — every answer carries
> verifiable clause citations, or the system abstains. Abstention is a feature,
> not a failure.

Open-source hybrid-retrieval infrastructure for regulated engineering domains
(ECSS / EASA CS / FAA FAR / NASA-STD). Engineers waste hours grep-ing
thousand-page PDFs where "clause 5.4.2.1b" must match *exactly*; generic RAG
chatbots hallucinate clause numbers. In a regulated domain a wrong citation is
worse than no answer.

**Status:** Weeks 0–4 done (spec §15) — ingestion, hybrid retrieval, the eval
harness, generation + abstention gates, and an end-to-end browser demo
(`/ask`, `/library`, `/documents/[slug]`) all work against a live corpus. See
[`GROUNDCITE_PROJECT_SPEC.md`](GROUNDCITE_PROJECT_SPEC.md) — the single source of
truth — and [`CLAUDE.md`](CLAUDE.md) for the coding conventions that gate every
change.

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
uploads new ones.

## Corpus & licensing

PDFs **never** enter git (size + license). `scripts/fetch_corpus.py` downloads
from official sources; `documents.license_note` is mandatory on every ingested
standard. Default demo corpus is **14 CFR Part 25** (US public domain) plus
released NASA standards. See spec §13.

## Roadmap

Ingestion, hybrid retrieval, the eval harness, generation + abstention gates,
and the `/ask` + `/library` + `/documents/[slug]` web UI shipped across Weeks
0–4 (spec §15) — see [`docs/WEEK3_RESULTS.md`](docs/WEEK3_RESULTS.md) and
[`docs/WEEK4_RESULTS.md`](docs/WEEK4_RESULTS.md) for real numbers and
transcripts. Week 5 adds the `/evals` page, README/demo polish, and closes
the residuals both results docs flag. The differentiator is a public,
reproducible **eval harness** with real retrieval numbers (recall@k, MRR,
citation precision, faithfulness) that gates every change in CI — including the
honest first baseline.

## License

[Apache-2.0](LICENSE).
