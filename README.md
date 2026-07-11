# GroundCite

> **Grounded Q&A over aerospace & engineering standards** — every answer carries
> verifiable clause citations, or the system abstains. Abstention is a feature,
> not a failure.

Open-source hybrid-retrieval infrastructure for regulated engineering domains
(ECSS / EASA CS / FAA FAR / NASA-STD). Engineers waste hours grep-ing
thousand-page PDFs where "clause 5.4.2.1b" must match *exactly*; generic RAG
chatbots hallucinate clause numbers. In a regulated domain a wrong citation is
worse than no answer.

**Status:** Pre-code skeleton (prep task **P5**). See
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

## Quickstart (skeleton)

```bash
# 1. Start Postgres (pgvector) and apply the schema
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

Config lives in `.env` (copy from [`.env.example`](.env.example)); it is the
single source of environment for every layer.

## Corpus & licensing

PDFs **never** enter git (size + license). `scripts/fetch_corpus.py` downloads
from official sources; `documents.license_note` is mandatory on every ingested
standard. Default demo corpus is **14 CFR Part 25** (US public domain) plus
released NASA standards. See spec §13.

## Roadmap

Ingestion, hybrid retrieval, the eval harness, generation + abstention gates,
and the web UI land across Weeks 1–5 (spec §15). The differentiator is a public,
reproducible **eval harness** with real retrieval numbers (recall@k, MRR,
citation precision, faithfulness) that gates every change in CI — including the
honest first baseline.

## License

[Apache-2.0](LICENSE).
