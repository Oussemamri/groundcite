# GroundCite — Grounded Q&A over Aerospace & Engineering Standards

> **One-liner:** An open-source hybrid-retrieval engine that answers questions about aerospace/engineering standards with exact clause citations — and refuses to answer when it can't ground the response.
>
> **Status:** Spec v1.0 — pre-code. This file is the single source of truth. If code and spec disagree, fix one of them in the same PR.

**Naming note:** Primary name `GroundCite` (grounded answers + citations + aerospace "ground segment"). Alternates if taken on GitHub/PyPI: `Normlume` (sibling branding to Reqlume), `ClauseZero`. Whatever you pick, find-replace once and never rename again.

---

## 1. Why this exists (positioning — keep this straight in README and blog posts)

- Engineers working under ECSS / EASA CS / FAA FAR / NASA-STD regimes waste hours grep-ing thousand-page PDFs where "clause 5.4.2.1b" must match *exactly* and paraphrases are dangerous.
- Generic RAG chatbots hallucinate clause numbers. In regulated domains a wrong citation is worse than no answer.
- GroundCite's contract: **every answer carries verifiable clause citations, or the system abstains.** Abstention is a feature, not a failure.
- Differentiator vs. the 1,000 RAG demos on GitHub: **a public, reproducible eval harness with real retrieval numbers** (recall@k, MRR, citation precision, faithfulness) that gates every change in CI.

**Non-marketing positioning for the CV/blog:** "Open-source retrieval infrastructure for regulated engineering domains" — sibling to Reqlume, not a competitor to it.

---

## 2. Theme & consistency rules

### 2.1 Domain language (use EVERYWHERE — code, DB, API, UI)
| Term | Meaning | Never call it |
|---|---|---|
| `Document` | One standard (e.g., "14 CFR Part 25", "ECSS-E-ST-40C") | file, pdf, source |
| `Section` | A node in the document's clause hierarchy (5.4.2) | heading, chapter |
| `Chunk` | A retrievable text unit tied to a Section | passage, snippet, fragment |
| `Ask` | A user question → pipeline run | query (reserved for DB), chat, prompt |
| `Citation` | Link from an answer sentence to a Chunk | reference, source |
| `Abstention` | Grounding gate failed → structured "cannot answer" | refusal, error |
| `Suite / Case / Run` | Eval terminology | test (reserved for pytest) |

### 2.2 Visual theme ("mission control")
- Background `#0B0E14` (near-black), surface `#131822`, border `#232B3A`.
- Text `#E6EAF2`; accents: **grounded green** `#2FBF71`, **abstained amber** `#F5A623`, link cyan `#4CC3FF`.
- Fonts: Inter (UI), **JetBrains Mono for every clause ID, standard code, and score** — monospace clause IDs are a signature detail.
- UI copy tone: calm, aviation-flavored, never cute in errors. Abstention card title: "No grounded answer" (subtitle: "Confidence below threshold — closest passages shown below."). Do not joke in abstentions.
- Every answer shows a status chip: `GROUNDED` (green) or `ABSTAINED` (amber) + retrieval confidence.

### 2.3 Naming conventions
- Repo/package: `groundcite`. Python package `groundcite`, CLI `groundcite`, Docker images `groundcite-api`, `groundcite-web`.
- Aerospace flavor lives in **UI copy and docs only**. Code uses plain domain language above. No `RocketRetriever` classes.

---

## 3. Scope

### 3.1 v1 goals (all must be true to call it done)
1. Ingest structured PDFs of standards into a clause-aware hierarchy (Postgres).
2. Hybrid retrieval (dense + lexical + clause-ID fast path) fused with RRF, optional reranker.
3. Answers with inline citations `[ECSS-E-ST-40C §5.4.2.1]` that resolve to real chunks, streamed over SSE.
4. Abstention gate with tunable thresholds; abstentions show best passages.
5. Eval harness: ≥60 golden cases, `groundcite eval run` produces a scored report; CI runs a smoke suite.
6. Web UI: Ask page with citation side-panel + document reader with clause tree + eval dashboard.
7. English + German questions over an English corpus (multilingual embeddings handle this).
8. README with architecture diagram, demo GIF, and honest benchmark table.

### 3.2 Explicit non-goals for v1 (write these in README too — scope armor)
- No fine-tuning, no training. Inference only.
- No user accounts/auth (single-tenant, local-first). RBAC is a v2 extension.
- No DOORS/ReqIF ingestion (that's Reqlume territory; keep the projects distinct).
- No agentic multi-step tool use. One ask = one pipeline run.
- No Kubernetes. Docker Compose only.
- No scanned-PDF OCR (require text-layer PDFs in v1).

---

## 4. Architecture — ports & adapters (hexagonal), strict dependency rule

```
┌────────────────────────────────────────────────────────────┐
│  INTERFACES            apps/api (FastAPI)   apps/web (Next)│
│                        cli (Typer)                         │
├────────────────────────────────────────────────────────────┤
│  APPLICATION SERVICES  IngestionService  AskService        │
│  (core/services)       EvalService       LibraryService    │
├────────────────────────────────────────────────────────────┤
│  DOMAIN (core/domain)  Document Section Chunk Ask Answer   │
│  pure python, zero I/O Citation AbstentionReason EvalCase  │
├────────────────────────────────────────────────────────────┤
│  PORTS (core/ports)    EmbeddingProvider  LLMProvider      │
│  Protocol classes      Reranker  VectorIndex  LexicalIndex │
│                        DocumentParser  StructureDetector   │
│                        Chunker  TokenCounter  Repository   │
├────────────────────────────────────────────────────────────┤
│  ADAPTERS (adapters/)  openai_embed  bge_m3_embed          │
│                        groq_llm  openai_llm  ollama_llm    │
│                        bge_reranker  llm_reranker          │
│                        pg_vector  pg_lexical  pg_repo      │
│                        docling_parser  pymupdf_parser      │
│                        cfr_structure  ecss_structure       │
│                        clause_chunker  bge_m3_tokencount   │
└────────────────────────────────────────────────────────────┘
```

**Dependency rule (enforce with import-linter in CI):**
`domain` imports nothing internal → `ports` import domain → `services` import domain+ports → `adapters` import domain+ports (NEVER services) → `apps/cli` import services + a `container.py` factory that wires adapters from config. **Core never imports an adapter.** This is the "clean layers for expansion" guarantee: adding Qdrant or Anthropic later = one new adapter file + one config value.

### 4.1 Repository layout (monorepo)
```
groundcite/
├── GROUNDCITE_PROJECT_SPEC.md      # this file
├── CLAUDE.md                       # coding conventions (seed in §15)
├── README.md
├── docker-compose.yml              # postgres(pgvector), api, web, [ollama]
├── .env.example
├── core/                           # pip-installable python package
│   ├── groundcite/
│   │   ├── domain/                 # entities.py, results.py (pydantic v2, frozen)
│   │   ├── ports/                  # protocols.py
│   │   ├── services/               # ingestion.py, ask.py, eval.py, library.py
│   │   ├── adapters/               # one module per adapter, grouped by port
│   │   ├── config.py               # pydantic-settings; single source of env
│   │   ├── container.py            # build_services(config) -> Services
│   │   └── cli.py                  # typer app
│   ├── tests/                      # unit (fakes for ports) + integration (pg)
│   └── pyproject.toml              # uv, ruff, mypy --strict on domain/ports/services
├── apps/
│   ├── api/                        # FastAPI, thin: routes -> services
│   │   └── app/ (routes/, sse.py, deps.py, main.py)
│   └── web/                        # Next.js 15, TS strict, TanStack Query
│       └── app/ (ask/, library/, documents/[id]/, evals/)
├── evals/
│   ├── suites/core.jsonl           # golden cases (committed)
│   ├── suites/german.jsonl
│   └── suites/negative.jsonl      # must-abstain cases
├── scripts/
│   ├── fetch_corpus.py             # downloads demo corpus (never commit PDFs)
│   └── seed_demo.py
└── .github/workflows/ci.yml        # lint, typecheck, unit, eval-smoke
```

---

## 5. Data model (Postgres 16 + pgvector)

```sql
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
```

Migrations: Alembic from day one, even solo. German corpus later: add a `tsv_de` column with `'german'` config rather than overloading `tsv`.

---

## 6. Ingestion pipeline (`IngestionService.ingest(pdf_path, doc_meta)`)

**Type seam (binding — resolved ambiguities, see §6.1 changelog):**
```python
# core/ports/protocols.py
class DocumentParser(Protocol):
    def parse(self, pdf_path: Path) -> ParsedDocument: ...

class StructureDetector(Protocol):
    def detect(self, doc: ParsedDocument) -> tuple[list[Section], SectionTextMap]: ...
    # SectionTextMap = Mapping[section_id, str]  -- raw text span per section,
    # kept OUT of the Section domain entity (Section stays a pure tree node
    # matching the `sections` table 1:1). This is the parallel-text-map seam.

class Chunker(Protocol):
    def chunk(
        self,
        doc: ParsedDocument,
        sections: list[Section],
        section_text: SectionTextMap,
        count_tokens: Callable[[str], int],   # injected, see §6.1 note on tokenizer
    ) -> list[Chunk]: ...

class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...
```

1. **Parse** — two adapters behind the `DocumentParser` port:
   - `docling_parser` (default): Docling gives layout, reading order, headings, and tables; export to its structured JSON, not markdown, so page numbers survive. Heavy dependency (pulls ML models) — isolate in an optional extra `groundcite[docling]`.
   - `pymupdf_parser` (fallback / lite): raw text + page numbers + font-size/bold signals. Keep it working — it's the CI-fast path and the air-gapped path.
   Both share ONE port contract test (`tests/ports/test_document_parser_contract.py`) so a second adapter can never silently drift from the first.

2. **Structure detection** — its own port, `StructureDetector`, NOT a private step inside the parser and NOT inlined in the chunker. Reasons this is binding: (a) it must be fake-testable per CLAUDE rule 3 without a real PDF, (b) organization-specific numbering (ECSS/NASA numeric hierarchy vs. FAA/EASA CFR-style `§ 25.1309`, `(a)(1)(i)`) must be swappable per `documents.organization` without touching the chunker, (c) it is exactly the seam future orgs (ESA, EASA) plug into.
   - Adapters: `cfr_structure` (this session), `ecss_structure` (later, spec §16).
   - Returns `(sections, section_text)` — the Section tree for persistence, plus a parallel `SectionTextMap` giving the chunker raw text per section without polluting the `Section` domain entity with a `raw_text` field it doesn't otherwise need.
   - Unmatched text attaches to the nearest preceding section. Fail loudly (raise, don't warn) if <90% of document text ends up attached to some section.

3. **Clause-aware chunking** (the quality lever — see §14 prep task), via the `Chunker` port, `clause_chunker` adapter:
   - Consumes `(doc, sections, section_text, count_tokens)` — the chunker NEVER imports an embedding library directly. Token counting is injected as a callable so swapping the embedding provider swaps the token counter in lockstep, wired once in `container.py`. Default counter: `bge_m3_tokencount` adapter (tokenizer from the same model as `bge_m3_embed`) — using the target embedder's own tokenizer as the token-count source of truth keeps size limits accurate for whichever embedder is actually configured; cache the loaded tokenizer (do not reload per call).
   - One chunk per leaf clause when ≤ ~450 tokens (per `count_tokens`); split long clauses on sentence boundaries with 60-token overlap.
   - **Merge rule (config, not hardcoded):** a leaf clause with no children and `token_count < MIN_LEAF_TOKENS` (default `64`) merges up into its parent's chunk. `MIN_LEAF_TOKENS` lives in `config.py` / `.env.example` alongside `TAU_RETRIEVAL` etc.
   - **Prepend a breadcrumb header to every chunk's `content`:**
     `[ECSS-E-ST-40C §5.4.2.1 — Software requirements > Verification > Test coverage]`
     This single trick massively improves both dense and lexical retrieval on standards. Breadcrumb title comes from the `Section` tree walked from the chunk's `section_id` to the document root — this is why §2 formalizes `Section` as carrying `title` but not raw text.

4. **Embed** in batches via `EmbeddingProvider`; store.
5. **Report**: sections found, chunks created, token histogram, orphan-text warnings. Fail loudly on <90% text attached to sections.

Idempotency: re-ingesting a `slug` replaces sections/chunks in one transaction.

### 6.1 Ambiguity-resolution changelog (do not re-litigate without a new PR)
| # | Decision | Rationale |
|---|---|---|
| 1 | Chunker signature is `chunk(doc, sections, section_text, count_tokens)` | Keeps `Section` a pure tree node; text and tokenization are explicit injected inputs, not hidden imports. |
| 2 | Structure detection is a first-class `StructureDetector` port, not inlined | Fake-testable (CLAUDE rule 3); swappable per organization without touching the chunker; the designed seam for §16's ECSS/NASA extension. |
| 4 | Token counting uses the configured embedder's own tokenizer, injected as a `TokenCounter` port/callable — never a direct adapter-to-adapter import | Chunk sizes stay correct for whichever embedder is active; adapters remain decoupled from each other, wired only through `container.py`. |
| 5 | Leafless clause merges into parent when `token_count < MIN_LEAF_TOKENS` (default 64) | Configurable — avoids hardcoding a magic number in the chunker; standards vary in how granular their smallest clauses are. |

---

## 7. Ask pipeline (`AskService.ask(question, filters) -> stream of AskEvents`)

```
question
  → [0] language + clause-ID detection        (regex: \b\d+(\.\d+)+[a-z]?\b, '§ 25.1309', 'ECSS-…')
  → [1a] dense candidates:   top-30 by cosine (HNSW)
  → [1b] lexical candidates: top-30 by ts_rank_cd(websearch_to_tsquery)
  → [1c] clause fast path:   exact clause_path matches (if [0] hit) — injected at rank 1
  → [2] RRF fusion: score(c) = Σ 1/(60 + rank_i(c)); keep top-20
  → [3] rerank (optional, config): bge-reranker-v2-m3 cross-encoder → top-6
  → [4] GATE A (retrieval): top score < τ_retrieval → ABSTAIN(reason=weak_retrieval)
  → [5] generate: LLM with structured output (see contract below)
  → [6] GATE B (citation validity): every cited chunk_id ∈ provided set, ≥1 citation
        per answer paragraph; else one repair retry, then ABSTAIN(reason=uncited)
  → [7] persist ask + citations + pipeline_debug; stream final payload
```

**Generation contract (system prompt for the answerer, keep in `core/services/prompts/`):**
- Input: question + the 6 chunks, each tagged `<chunk id="…" clause="…">`.
- Output JSON: `{ "answer_md": str, "citations": [{"chunk_id": str, "claim": str}], "insufficient": bool }`.
- Rules in prompt: answer ONLY from chunks; every factual sentence maps to ≥1 citation; if chunks don't contain the answer set `insufficient: true` (feeds Gate B); answer in the question's language; clause IDs verbatim in monospace-friendly form `§5.4.2.1`.

**Abstention payload** is a first-class result: `{status: "abstained", reason, top_passages: [...]}` — UI renders passages so an abstention is still useful.

**SSE event types** (API and web must share this enum): `stage` (`retrieving|reranking|generating`), `token`, `citations`, `final`, `error`.

Defaults to start (tune with evals, store in config not code): `τ_retrieval = 0.35` (reranker score) or RRF `≥ 0.05` when reranker off; candidates 30/30 → fused 20 → context 6.

**§7.1 Amendment (Week 3 Phase 6, tuned with real evals as this section itself
instructs):** the "RRF ≥ 0.05 when reranker off" fallback is DEAD — Week 2
measured that with `rrf_k=60` and two candidate lists, the RRF ceiling is
`2/61 ≈ 0.033`, below 0.05 itself, and grounded/must-abstain RRF distributions
overlap completely (Gate A cannot separate them on RRF alone). **Gate A
therefore REQUIRES the reranker**; `ask()` raises a config error if
`RERANKER_ENABLED=false`. `τ_retrieval` is raised from `0.35` to `0.70`: a real
60-case full-pipeline baseline (`docs/WEEK3_RESULTS.md`) swept τ against every
case's recorded top_score and found 0.35 leaks 3/12 (25%) must-abstain cases
through Gate A on raw score alone; 0.70 is the first τ with zero measured leak.
Cost: grounded-wrongly-abstained rises 4.2% → 10.4% (5/48) — spec §1's "wrong
citation is worse than no answer" contract justifies the trade.

---

## 8. Evals (`EvalService`) — the differentiator, build BEFORE the UI

- **Case types** (target ≥60 total, committed as JSONL):
  1. Direct clause lookup — "What does §25.1309(b) require?" (15)
  2. Semantic — "What failure probability is acceptable for catastrophic conditions?" (15)
  3. Cross-clause synthesis (10)
  4. **Negative / out-of-corpus — must abstain** ("What does DO-178C say about MC/DC?" when DO-178C isn't ingested) (10)
  5. German-language questions on English corpus (10)
- **Metrics per case:** recall@5, recall@10, MRR over `expected_clauses`; citation_precision (cited clauses ⊆ relevant); faithfulness (LLM-judge: does each cited chunk entail its claim? judge model ≠ answer model); abstention correctness for negative cases.
- **Implementation policy (build vs. buy):** hand-roll recall@k, MRR, citation_precision, and abstention checks (they're ~15 lines each and we need per-case debug detail). Import **Ragas** ONLY for LLM-judge metrics (faithfulness, context precision). The judge model name + version MUST live in config and be written into `eval_runs.config` — swapping the judge invalidates historical comparisons. Optionally use Ragas's synthetic dataset generator to DRAFT golden cases (P2), but every expected clause is human-verified before commit.
- **Run mechanics:** `groundcite eval run --suite core` → writes `eval_runs` + prints table + writes `evals/reports/<sha>.md`. Config snapshot stored so runs are comparable.
- **CI gate:** 12-case smoke suite; fail PR if recall@5 drops >5pts vs. baseline file `evals/baseline.json`. Tolerance bands, never exact thresholds — LLM-judge output is non-deterministic and exact gates flake. Retrieval-only smoke cases (no judge) are the most stable CI signal; run judge metrics nightly or on demand, not per-commit.
- **Honesty rule:** README benchmark table shows current real numbers, including the embarrassing first baseline. The blog post narrative is the *improvement*, which requires committing the bad baseline.

---

## 9. API surface (FastAPI, `/api/v1`)

| Method & path | Purpose |
|---|---|
| `POST /asks` | body `{question, document_slugs?}` → SSE stream (§7 events) |
| `GET /asks/{id}` | replay a past ask (answer + citations + debug) |
| `POST /documents` | multipart PDF + metadata → `{job_id}` (BackgroundTask in v1) |
| `GET /documents` / `GET /documents/{slug}` | library + clause tree |
| `GET /chunks/{id}` | citation resolution target |
| `POST /eval/runs` / `GET /eval/runs` / `GET /eval/runs/{id}` | trigger + read eval runs |
| `GET /healthz` | db + provider reachability |

Rules: routes are thin (parse → service → serialize); pydantic response models shared nowhere with domain entities (map explicitly); errors as RFC-7807 problem JSON.

**CLI (typer, same services):** `groundcite ingest <pdf> --slug far-25 …`, `groundcite ask "…" [--json]`, `groundcite eval run --suite core`, `groundcite eval report <run-id>`.

## 10. Web app (Next.js 15, App Router, TS strict, TanStack Query, Tailwind)

- `/ask` — input + streaming answer; **right panel: citation cards** (clause_path mono, snippet, score); clicking a citation opens the reader anchored & highlighted. Status chip GROUNDED/ABSTAINED per §2.2.
- `/library` — documents table (org, code, version, chunks, license_note) + upload with ingestion progress.
- `/documents/[slug]` — reader: left clause tree, right content, `?chunk=` deep-link highlights.
- `/evals` — runs table + per-suite metric trend (recharts) + per-case drill-down showing retrieved-vs-expected clauses. **This page is the screenshot for the blog post.**
- SSE via `fetch` + ReadableStream (typed event parser in `lib/sse.ts` mirroring §7 enum).

## 11. Tech decisions & rationale (defaults; all swappable via ports)

| Concern | Default | Why | Alternate adapter |
|---|---|---|---|
| Store (vector+lexical+relational) | **Postgres 16 + pgvector** | one system, prod-credible, matches your stack | qdrant (v2) |
| Embeddings | **BAAI/bge-m3** local (1024-d, multilingual) | free, OSS-friendly, handles DE↔EN | `openai text-embedding-3-*` |
| Generator | **Groq-hosted Llama** (fast/cheap) | streaming demo feel | OpenAI, Ollama (fully local mode) |
| Reranker | **bge-reranker-v2-m3** (CPU ok at top-20) | big precision win, free | LLM-rerank |
| Judge (evals only) | strongest model you have API access to | judge ≠ answerer | — |
| PDF parsing | **Docling** (`docling`) | layout + reading order + tables, local-first | PyMuPDF (lite/CI path) |
| Embedding/reranker inference | **FlagEmbedding** (bge-m3, `normalize=True` reranker scores feed τ_retrieval) | canonical BGE package, MIT | sentence-transformers |
| Reranker abstraction | **rerankers** (AnswerDotAI) | unified API, zero deps; our Reranker port wraps it | direct FlagEmbedding |
| Eval judge metrics | **Ragas** (faithfulness, context precision ONLY) | canonical, academically grounded | DeepEval |
| LLM client (all 3 generation providers) | **`openai` SDK** — one OpenAI-compatible client serves Groq (`api.groq.com/openai/v1`), OpenAI, and Ollama (`localhost:11434/v1`) | zero custom SSE/HTTP; §11.1 "model inference (generate)" = Buy; port stays swappable | hand-rolled httpx streaming |
| Python tooling | uv, ruff, mypy(strict core), pytest, Alembic | modern, fast | — |
| **API SSE plumbing** | **`sse-starlette`** (`EventSourceResponse` over the sync `ask()` generator; starlette iterates sync iterators in a threadpool) | spec §11.1 Buy; spec §7 one event enum shared with web | hand-rolled raw `StreamingResponse` (rejected: headers/keep-alive/disconnect handling) |
| **API logging** | **`structlog`** (JSON to stdout, API layer only; core stays logfree) | spec §12 names it; `ask_id` bound per request | stdlib `logging` |
| **API multipart uploads** | **`python-multipart`** (FastAPI requires it for `POST /documents`) | spec §9 | hand-rolled multipart parser (rejected) |
| **API test client** | **`httpx`** (Starlette `TestClient` requires it; DEV-only, not runtime) | AD-7 unit tests via `dependency_overrides` | — |
| **API server** | **FastAPI + uvicorn[standard]** | spec §9 (= Buy; the routes/services are Build) | — |
| Verify model names + library versions at build time — this landscape changes monthly. Pin everything (§17 rule 12; `apps/api` deps pinned `==`, `uv.lock` + `package-lock.json` committed). | | | |

### 11.1 Build vs. buy boundary (the line you defend in interviews)
**Buy (libraries):** PDF parsing, model inference (embed/rerank/generate), judge-metric math, SSE plumbing (`sse-starlette`), DB drivers (`pgvector-python` — steal its hybrid-search SQL shapes).
**Build (ours, always):** clause-tree construction, clause-aware chunking + breadcrumbs, hybrid fusion (RRF) + clause fast-path, abstention gates A/B, retrieval metrics, the eval runner/report/CI gate, all prompts.
**Never introduce:** LangChain, LlamaIndex, Haystack, or any RAG orchestration framework. The pipeline in §7 is the portfolio piece; frameworks hollow it out. Reference their source if useful — never depend on it.

Config via `.env` (see `.env.example`): `DATABASE_URL`, `EMBEDDING_PROVIDER=bge_m3|openai`, `LLM_PROVIDER=groq|openai|ollama`, `RERANKER_ENABLED=true`, `TAU_RETRIEVAL=0.70` (§7.1 amendment), `MIN_LEAF_TOKENS=64`, provider keys.

## 12. Observability (interviewers probe this)

- structlog JSON logs; every ask gets `ask_id` propagated through stages.
- `pipeline_debug` jsonb per ask: stage timings ms, candidate lists with scores pre/post fusion/rerank, token counts, cost. The `/asks/{id}` page renders it — built-in tracing without extra infra.
- `/healthz` checks DB + one cheap provider call.

## 13. Corpus & legality (DO THIS FIRST — prep task P1)

| Corpus | Status | Use |
|---|---|---|
| **14 CFR Part 25 (FAA FARs)** | US public domain | ✅ default demo corpus, redistributable |
| **NASA-STD-8739.x / 8719.x** | publicly released | ✅ demo corpus |
| **EASA CS-25 / AMC** | public on easa.europa.eu | ✅ fetch-script; verify redistribution before committing text |
| **ECSS standards** | free download after registration on ecss.nl | ⚠️ fetch-script only; do NOT commit PDFs; check terms |
| **DO-178C / ARP4754A** | RTCA/SAE paywalled | ❌ never ship; "bring your own PDF" path only |

Rules: PDFs never enter git (size + license); `scripts/fetch_corpus.py` downloads from official sources; `documents.license_note` is mandatory; README gets a "Corpus licensing" section. This diligence is itself a talking point for regulated-industry employers.

## 14. Preparation checklist (before writing app code)

- **P1 — Corpus (½ day):** run through §13, download FAR Part 25 + 2 NASA STDs + 1 EASA CS. Skim structure of each; note numbering quirks per org (feeds §6 regexes).
- **P2 — Golden set (1–1.5 days, the most valuable prep):** write the ≥60 eval cases (§8 mix) BEFORE building retrieval. Draft with an LLM or Ragas's synthetic generator from the PDFs, then manually verify every expected clause — no unverified case enters the JSONL. This is test-first RAG and the core of the blog story.
- **P3 — Chunking dry-run (½ day):** notebook: parse FAR Part 25 with BOTH Docling and PyMuPDF, compare structure quality, print detected clause tree, eyeball 20 random chunks with breadcrumbs. Iterate regexes until <10% orphan text. Also compare our clause chunker vs. Docling's HybridChunker on 20 chunks — whichever loses, the comparison is a blog-post paragraph.
- **P4 — Model matrix (½ day):** confirm current Groq/OpenAI model names + prices; measure bge-m3 + reranker latency on your machine (CPU vs. small GPU); pick embedding dims (1024) and lock — changing dims later = full re-embed.
- **P5 — Repo skeleton (½ day):** layout from §4.1, docker-compose (pgvirtual: `pgvector/pgvector:pg16`), CI (ruff+mypy+pytest+import-linter), Apache-2.0 LICENSE, this file + CLAUDE.md committed. First commit = skeleton + spec, no features.
- **P6 — Name check (30 min):** GitHub org/repo, PyPI, domain if you care. Lock it.

## 15. Milestones (part-time, ~5 weeks — resist reordering)

| Week | Deliverable | Proof it's done |
|---|---|---|
| 0 | P1–P6 prep | golden JSONL committed; skeleton CI green |
| 1 | Schema + ingestion + `groundcite ingest` | FAR-25 ingested; ingestion report clean |
| 2 | Hybrid retrieval + fusion + `groundcite ask` (retrieval-only mode) + **retrieval-only eval metrics** | top-6 chunks printed with scores for 10 sample questions; `eval run --retrieval-only` reports a real recall@5/recall@10/MRR baseline |
| 3 | **Judge eval metrics + first full baseline** + generation + gates | `eval run` report committed with real (bad) numbers; then tune: chunking → +rerank → thresholds; each change = a run |

**§15.1 Amendment (Week 2, agreed):** the *retrieval half* of §8 — recall@k, MRR,
and the eval runner/report — moves from Week 3 into Week 2. Rationale: Week 2 is
where retrieval and fusion are actually built, and CLAUDE.md rule 4 requires an
eval run for every change to them; without this, Week 2's only quality bar is
eyeballing 10 questions and every Week-3 tuning decision is retro-justified.
These metrics are pure arithmetic over `expected_clauses` — no judge, no LLM, no
Ragas, no new dependency — and §8 already names retrieval-only cases "the most
stable CI signal". The *judge half* (faithfulness, context precision, Ragas,
generation, Gates A/B) stays in Week 3 as written. This splits §8 along a seam
§8 itself draws; it does not reorder the milestones wholesale.
| 4 | FastAPI + SSE + `/ask` and `/documents` pages | end-to-end demo in browser |
| 5 | `/evals` page, abstention polish, README + demo GIF, **blog post: "Recall@5 from X→Y on FAR Part 25"** | repo public, post published, link on CV |

Scope armor: after week 5, only bugfixes + the blog post. New ideas go to `docs/ROADMAP.md`, not to code.

## 16. Extension paths (designed-for, not built)

New vector store / LLM / embedder = new adapter + config value. Then, in rough order of value: German corpus (`tsv_de`), scanned-PDF OCR adapter, ReqIF parser (bridge to Reqlume), multi-tenant + RBAC, agentic multi-hop asks, MCP server exposing `ask`/`search_clauses` as tools (nice: connects this project to your MCP experience), Qdrant adapter at scale.

## 17. CLAUDE.md seed (copy into repo root; steering rules for AI-assisted coding)

```markdown
# GroundCite — rules for AI-assisted development
1. Read GROUNDCITE_PROJECT_SPEC.md before any task. If a request conflicts
   with the spec, say so and stop.
2. Dependency rule is law: domain ← ports ← services / adapters ← apps.
   Core never imports adapters. import-linter enforces; don't fight it.
3. Every service-layer change ships with unit tests using fake ports
   (no network, no DB). Integration tests may use the compose Postgres.
4. Any change to chunking, retrieval, fusion, thresholds, or prompts MUST
   include an eval run: `groundcite eval run --suite core` — paste the
   before/after table in the PR/commit message.
5. mypy --strict on core; no `Any` in ports; pydantic v2 frozen models in domain.
6. TS: strict, no `any`, TanStack Query for all server state, SSE types
   mirror core/services enums exactly.
7. Small diffs. One feature per commit. Conventional commits (feat:, fix:,
   eval:, docs:).
8. Domain language from spec §2.1 everywhere. No synonyms.
9. Secrets only via config.py/pydantic-settings. Never hardcode model names
   outside config defaults.
10. When unsure between clever and boring: boring.
11. Build-vs-buy boundary (spec §11.1) is law: NEVER add LangChain, LlamaIndex,
    Haystack, or any RAG framework. Allowed libs: docling, flagembedding,
    rerankers, ragas (judge metrics only), sse-starlette, pgvector. Anything
    new goes through a spec §11 table update first.
12. Pin every dependency version. Judge model name lives in config and is
    snapshotted into every eval run.
```

---
*End of spec. First action: prep task P1.*