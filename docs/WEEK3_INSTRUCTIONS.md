# Week 3 — Generation + Gates A/B + judge evals: execution instructions

> Audience: the AI engineer (model) executing Week 3. Read this WHOLE file, then
> `GROUNDCITE_PROJECT_SPEC.md` (§7, §8, §11, §12, §15) and `CLAUDE.md`, before
> writing any code. Where this file says "DECIDED", the architecture call has
> already been made with the repo owner — implement it, do not re-litigate it.
>
> Deliverable (spec §15 Week 3): **`groundcite eval run` report committed with
> real (possibly embarrassing) full-pipeline numbers — generation, Gates A/B,
> judge metrics — then tune thresholds, each change carrying an eval run.**

---

## 0. Non-negotiable rules (violations = rejected work)

1. **Read the spec first** (CLAUDE.md rule 1). If a task here conflicts with the
   spec, stop and say so — except where this file explicitly records a spec
   amendment step (the spec's own preamble: when code and spec disagree, fix one
   of them in the same PR).
2. **Dependency rule is law** (rule 2): domain ← ports ← services/adapters ←
   apps. Services never import adapters or config. import-linter enforces (5
   contracts); run it before every commit.
3. **Every service-layer change ships with unit tests using fake ports** (rule
   3) — no network, no DB, no model downloads in unit tests. Integration tests
   may use the compose Postgres and MUST auto-skip when it is unreachable (the
   `tests/integration/conftest.py` autouse guard is the pattern; CI runs no DB).
4. **Every change to retrieval, fusion, thresholds, or prompts ships with an
   eval run** (rule 4) — the harness exists now (`groundcite eval run`), so this
   is literal: paste the before/after table in the commit message.
5. **mypy --strict on core; no `Any` in ports; pydantic v2 frozen models in
   domain** (rule 5). Heavy optional-dep adapters get per-module mypy overrides
   in `core/pyproject.toml` — extend the EXISTING override block, don't invent
   a new mechanism.
6. **Build-vs-buy boundary** (rule 11 / spec §11.1): prompts, gates A/B, the
   eval runner, and all metrics except LLM-judge are BUILD (ours). NEVER add
   LangChain, LlamaIndex, Haystack, instructor, outlines, pydantic-ai, or any
   RAG/LLM orchestration framework. New libraries require the spec §11 table
   row FIRST, in the same commit (Phase 1 does exactly this for two libs).
7. **Pin every dependency version** (rule 12). Judge model name lives in config
   and is snapshotted into every eval run.
8. **NEVER create or modify anything under `evals/suites/`** (rule 13). That
   directory is human-owned. The golden set is read-only input. If a case looks
   wrong, report it — do not fix it.
9. **Domain language** (rule 8 / spec §2.1): Ask (not query/chat), Citation
   (not reference/source), Abstention (not refusal), Suite/Case/Run (not test),
   clause_path, GROUNDED/ABSTAINED. Enums in `domain/results.py` are the single
   source of truth — do not restate string literals.
10. **Small diffs, one feature per commit, conventional commits** (rule 7):
    `feat:`, `fix:`, `eval:`, `docs:`. Secrets only via config/pydantic-settings
    (rule 9) — model names live ONLY in config defaults.

**Working style** (CLAUDE.md rule 0): diagnose with evidence before coding
(when behavior surprises you, measure it — don't guess); failing test first for
every fix; boring beats clever; surgical diffs; state assumptions out loud.

---

## 1. Where the project stands (verified facts, 2026-07-14)

Weeks 0–2 are done and pushed; CI is green on `main`.

**Working today:**
- Ingestion: FAR-25 ingested clean — 3,291 sections, 1,573 chunks, real bge-m3
  1024-d embeddings, breadcrumb headers, appendices as top-level sections,
  page furniture stripped, print hyphenation healed (2 broken words remain,
  down from 5,591).
- Retrieval: `AskService.retrieve(question, document_slugs, top_k)` — clause-ID
  detection → dense (HNSW cosine) ∥ lexical (ts_rank_cd) ∥ clause fast-path →
  RRF fusion → optional cross-encoder rerank (normalized scores). LLM-free by
  design so evals never need a judge to measure retrieval.
- Eval harness (retrieval half): `groundcite eval run --suite core|german|negative
  --no-rerank --no-write-report` → recall@5/@10, MRR, per-case misses, report
  file. Metrics are hand-rolled in `services/metrics.py`.
- CLI: `groundcite ingest`, `groundcite ask` (retrieval-only), `groundcite eval
  run` (retrieval-only). `groundcite eval report <run-id>` is a stub.

**Measured baseline you are building on (final corpus, sha `2c7b56c`):**

| metric | rerank OFF | rerank ON |
|---|---|---|
| core recall@5 | 0.800 | 0.863 |
| core recall@10 | 0.879 | 0.902 |
| core MRR | 0.853 | 0.850 |
| german recall@10 | 0.958 | 0.958 |

**Gate A evidence (the numbers your gate design must respect):**
- Normalized reranker top-scores: grounded (n=48) min 0.0530 / median 0.9487 /
  max 0.9996; must-abstain (n=12) min 0.0005 / median 0.0417 / max 0.6891.
- 5/48 grounded cases score ≤ the best must-abstain case → no τ is perfect.
- At spec's τ=0.35: 2/48 grounded wrongly abstained, **3/12 must-abstain wrongly
  answered (25% leak — unacceptable per §1)**.
- **RRF scores cannot gate**: with two lists and rrf_k=60 the ceiling is
  2/61 ≈ 0.0328, below the spec's "RRF ≥ 0.05" — and grounded/must-abstain RRF
  distributions overlap completely. Pinned by a unit test.
- Clause fast-path hits carry score 1.0 (`CLAUSE_FAST_PATH_SCORE`) and therefore
  pass any τ by construction — intended: an exact clause match never abstains.

**Gaps you will fill (verified in code, not guessed):**
- `adapters/llm/{groq,openai,ollama}_llm.py` are 4-line stubs. `LLMProvider`
  port exists: `stream(system, user) -> Iterator[str]`.
- `services/prompts/` contains only `__init__.py`.
- `AskService.ask()` does not exist (only `retrieve()`).
- `Repository.save_ask(ask)` persists the ask row but **not citations** — the
  `citations` table (ask_id, chunk_id, rank, score) exists in the schema with
  no writer. Port extension needed.
- `Repository.save_eval_run(run)` exists but nothing writes `eval_results`, and
  `eval_results.case_id` FK-references `eval_cases` — while the CLI loads cases
  from JSONL with deterministic uuid5 ids that are NOT in the DB. Persistence
  design in AD-6 resolves this.
- `evals/baseline.json` (spec §8 CI gate) does not exist.
- Domain types for everything already exist in `domain/results.py`: `AskEvent`,
  `AskEventType` (STAGE/TOKEN/CITATIONS/FINAL/ERROR), `Stage`, `AskStatus`,
  `AbstentionReason` (WEAK_RETRIEVAL/UNCITED), `Citation`, `Answer`,
  `Abstention`, `EvalRun`, `EvalResult`. Use them; extend only if forced.

**Known non-bugs (do not "fix"):**
- The one remaining core miss (§25.301/303 structure-strength case) is a
  question/clause vocabulary mismatch, not a pipeline defect.
- German lexical retrieval is weak by design (english tsvector); dense + clause
  fast-path carry it. `tsv_de` is a §16 extension — out of scope.
- 26 chunks remain >460 tokens (table-heavy appendices; tables have no sentence
  boundaries). Accepted residual.
- 2 verification-worksheet flags (§25.803, §25.857) were human-reviewed:
  false positives (stemming). Golden set is sound; freeze is the OWNER's task.

---

## 2. Look-outside survey (done — verdicts binding per rule 11)

| Candidate | Verdict | Why |
|---|---|---|
| **`openai` SDK** | **ADOPT** (pinned, `[llm]` extra) | One OpenAI-compatible client serves all three providers: Groq (`https://api.groq.com/openai/v1`), OpenAI, Ollama (`http://localhost:11434/v1`). Zero custom HTTP/SSE client code; §11.1 puts "model inference (generate)" under Buy. Requires spec §11 table row (Phase 1). |
| **`ragas`** | **ADOPT** (pinned, `[judge]` extra) | Spec §11 explicitly allows it for faithfulness + context precision ONLY. ⚠️ It pulls `langchain-core` transitively — acceptable ONLY because the spec names ragas; quarantine in the extra, import lazily inside the judge adapter, never import it in services. If integration proves heavy or flaky, the FALLBACK (pre-approved) is a hand-rolled judge prompt using the configured judge model — spec §11.1 keeps prompts as Build anyway. |
| `groq` SDK | reject | Redundant — Groq is OpenAI-compatible; one client, not three. |
| `httpx` hand-rolled streaming | reject | Reinventing SSE client plumbing the `openai` SDK already does; not on the allow-list. |
| `instructor` / `outlines` / `pydantic-ai` | reject | Orchestration frameworks; rule 11 "never". The JSON contract is parsed by hand (~30 lines + one repair retry) — it's part of the portfolio piece. |
| `langdetect` / `lingua` / fasttext | reject | A dependency for one DE/EN binary decision is unjustified; hand-roll a stopword-ratio heuristic (~15 lines, table-tested). |
| `tenacity` | reject | The Gate-B repair retry is a single explicit loop; stdlib suffices. |
| `deepeval` / `promptfoo` / `giskard` | reject | Alternate judge/eval frameworks; ragas is the spec's choice and the runner is Build. |
| `tiktoken` | reject | Token usage comes from the provider's `usage` response field. |

**Model names (rule: verify at build time — spec §11 last row).** This file was
written 2026-07; model catalogs rot. Before pinning config defaults, check the
providers' current model lists and confirm with the owner which API keys exist
(`GROQ_API_KEY`? `OPENAI_API_KEY`? local Ollama?). Reasonable starting points to
verify, not to trust: Groq `llama-3.3-70b-versatile` (answerer default),
OpenAI `gpt-4o-mini` (alternate answerer), judge = the strongest model the owner
has access to (spec §11: "judge ≠ answerer" is a hard rule).

---

## 3. Architecture decisions (DECIDED — implement, don't re-litigate)

**AD-1 — One OpenAI-compatible adapter, three factories.**
`adapters/llm/openai_compatible.py` implements `LLMProvider` around the `openai`
SDK (streaming chat completions; lazy import; guarded like `bge_reranker.py`).
`groq_llm.py`, `openai_llm.py`, `ollama_llm.py` become thin factories that bind
base_url + api_key + model from injected parameters. Container selects by
`settings.llm_provider`. New config (rule 9): `groq_model`, `openai_model`,
`ollama_model`, `judge_provider`, `judge_model`. `.env.example` updated in the
same commit. The adapter must also expose token usage per call (prompt +
completion tokens) — it feeds `pipeline_debug` and cost.

**AD-2 — `ask()` is a generator of `AskEvent`s layered on `retrieve()`.**
`AskService.ask(question, document_slugs) -> Iterator[AskEvent]`:
STAGE(retrieving) → [retrieve()] → STAGE(reranking happens inside retrieve; emit
it around the rerank timing] → Gate A → STAGE(generating) → TOKEN per streamed
token → parse → Gate B → CITATIONS → persist → FINAL (or ERROR). The Week-2
`retrieve()` method is called unchanged — no duplication of the retrieval steps.
CLI `groundcite ask` gains full mode (default when an LLM is configured) and
keeps `--retrieval-only`.

**AD-3 — Gate A gates on the NORMALIZED RERANKER score; reranker is REQUIRED
for generation mode.** Measured: RRF cannot separate grounded from must-abstain
(see §1). Therefore: if `RERANKER_ENABLED=false`, full-pipeline `ask()` raises a
clear config error at wiring time (retrieval-only mode continues to work without
it). The spec §7 line "or RRF ≥ 0.05 when reranker off" is amended in Phase 6
with the evidence — same-commit spec+config change, per the spec preamble.
τ stays `TAU_RETRIEVAL` from config; its DEFAULT changes only in Phase 6 as a
measured tuning commit (target: zero must-abstain leak on the negative suite —
the measured zero-leak point is τ just above 0.6891; expect ~0.70 — at a cost of
~10% wrongly-abstained grounded cases; the owner has already chosen the
zero-hallucination side of this trade, and Gate B plus the §7 abstention payload
soften the cost: an abstention still shows top passages).

**AD-4 — Generation contract exactly as spec §7, parsed by hand.**
Prompt in `core/groundcite/services/prompts/` (a python module holding string
constants + a renderer — chunks tagged `<chunk id="…" clause="…">`). Output JSON
`{"answer_md": str, "citations": [{"chunk_id": str, "claim": str}],
"insufficient": bool}`. Parser: strip code fences, `json.loads`, validate shape
— on failure ONE repair retry (re-prompt with the parse error), then
ABSTAIN(UNCITED). Mapping DECIDED: `insufficient: true` → ABSTAIN with reason
**WEAK_RETRIEVAL** (the model confirmed the retrieved context cannot answer —
that is a retrieval-strength verdict; UNCITED is reserved for citation-validity
failures). Record the convention in the module docstring.

**AD-5 — Gate B (ours):** every `citations[].chunk_id` must be in the provided
context set, ≥1 citation per answer paragraph (spec §7 step 6). Violation → one
repair retry (re-prompt naming the invalid ids / uncited paragraphs) → still
bad → ABSTAIN(UNCITED). Hand-rolled in services; exhaustively unit-tested with
a scripted FakeLLM (valid / invalid-id / uncited-paragraph / malformed-JSON /
insufficient / repair-succeeds / repair-fails).

**AD-6 — Persistence.** Extend the Repository port:
- `save_ask(ask, citations: Sequence[Citation])` — one transaction writing
  `asks` + `citations` rows (rank, score from the final context ranking).
- `save_eval_run(run, results: Sequence[EvalResult])` — one transaction that
  first UPSERTS the JSONL cases into `eval_cases` (their uuid5 ids are
  deterministic, so the FK holds and re-runs are idempotent), then writes
  `eval_runs` + `eval_results`.
- `get_eval_run(run_id)` + whatever minimal read the report command needs.
Update `tests/fakes.py::FakeRepository` in lockstep. `latency_ms` measured;
token usage always in `pipeline_debug`; `cost_usd` computed only when the model
has a price entry in an optional config map, else NULL — never fake a number.

**AD-7 — Judge metrics (evals only).** `citation_precision` and abstention
correctness are hand-rolled in `services/metrics.py` (same style as recall).
`faithfulness` (+ context precision if cheap) via ragas behind a `--judge` flag:
`groundcite eval run --suite core --judge`. Without the flag or without a key,
judge columns are NULL and the run still completes — retrieval + citation
metrics must never depend on a judge (spec §8: judge nightly/on-demand, not
per-commit). Judge model + version snapshotted into `eval_runs.config`.

**AD-8 — Baseline + comparator, CI wiring deferred.** Commit
`evals/baseline.json` (recall@5/@10, MRR, citation_precision, abstention
correctness per suite, at a named sha) and `scripts/check_baseline.py` (fails
if recall@5 drops >5 pts — tolerance bands per spec §8). DO NOT wire it into
GitHub Actions yet: CI has no Postgres and no embedded corpus; a seeded fixture
strategy is a Week-4 decision. Say this in the commit message rather than
shipping a gate that can't run.

---

## 4. Phase plan (execute in order; every step has a verify line)

### Phase 0 — Orientation (no code)
1. Read spec §7, §8, §11, §12, §15 + CLAUDE.md + this file. Read
   `services/ask.py`, `services/eval.py`, `services/metrics.py`,
   `domain/results.py`, `adapters/reranker/bge_reranker.py` (the lazy-import +
   mypy-override pattern you will copy), `tests/fakes.py`,
   `tests/integration/conftest.py`.
2. **OWNER GATE — ask, don't assume:** (a) which LLM API keys exist (Groq /
   OpenAI / local Ollama), (b) which model to use as judge (must ≠ answerer),
   (c) golden-set freeze status (worksheet found 0 real problems; freezing is
   the owner editing `evals/suites/` himself — never you).
   → **verify:** answers recorded at the top of your working notes/PR body.

### Phase 1 — Spec §11 amendment + dependencies + config
3. Add spec §11 table rows: `openai` SDK (LLM client, all three providers) and
   confirm the existing ragas row; add `[llm]` extra (`openai`, pinned) and
   `[judge]` extra (`ragas`, pinned) to `core/pyproject.toml`; config fields
   `groq_model`, `openai_model`, `ollama_model`, `judge_provider`, `judge_model`
   (+ optional price map) with VERIFIED current model names; `.env.example`.
   One commit: spec row + dep + config together (rule 11).
   → **verify:** `uv lock --check` clean; `uv sync --extra llm` installs;
   `get_settings()` round-trips; import-linter 5/5; CI (no extras) still green
   because all new imports are lazy.

### Phase 2 — LLM adapters
4. `openai_compatible.py` + three factories + container wiring (AD-1). Copy the
   guarded-import + pyproject mypy-override pattern from `bge_reranker.py`.
5. `FakeLLM` in `tests/fakes.py`: scripted token stream + scripted usage; a
   variant that yields different scripted responses per call (for repair-retry
   tests).
   → **verify:** unit tests — provider selection by config, stream order,
   usage capture, RuntimeError with install hint when extra missing. MANUAL
   smoke (owner-gated by keys): one real streamed completion via each available
   provider, transcript pasted in the commit message.

### Phase 3 — Prompts + parsing + language detection (all Build)
6. `services/prompts/answerer.py`: system prompt implementing every §7 contract
   rule (answer ONLY from chunks; every factual sentence cites; `insufficient`;
   answer in the question's language; clause IDs verbatim `§25.1309(b)`);
   context renderer producing `<chunk id="…" clause="…">` blocks. Also the
   repair-retry prompts (parse-error and citation-error variants).
7. `services/answer_parse.py`: fence-stripping JSON parser → `Answer` | parse
   error detail (for the repair prompt).
8. `services/lang_detect.py`: DE/EN stopword-ratio heuristic.
   → **verify:** table-driven unit tests: renderer output contains every chunk
   id exactly once; parser handles clean JSON / fenced JSON / trailing prose /
   malformed (returns error, never raises); lang_detect on the 10 german-suite
   questions → "de", 10 english → "en" (read the questions via the eval loader,
   which is read-only — rule 13).

### Phase 4 — `ask()` with Gates A and B
9. Implement AD-2/AD-3/AD-4/AD-5 in `services/ask.py`; extend the Repository
   port + `pg_repo` + `FakeRepository` per AD-6 (save_ask with citations).
10. CLI: full-mode `groundcite ask` (streams tokens to terminal, prints
    citations + GROUNDED/ABSTAINED status + latency; `--json` emits the final
    payload; `--retrieval-only` preserved).
    → **verify (rule 3):** unit tests with fakes covering: Gate A abstain
    (top score < τ) with top_passages payload; clause-fast-path bypass (score
    1.0 answers even with low τ… i.e. never gated); happy path GROUNDED with
    persisted ask+citations; invalid citation → repair → success; repair →
    still invalid → ABSTAIN(UNCITED); malformed JSON → repair → abstain;
    `insufficient` → ABSTAIN(WEAK_RETRIEVAL); reranker-off + full mode →
    config error. Event ORDER asserted (STAGE… TOKEN… CITATIONS, FINAL last,
    exactly one terminal event). Integration: one real `groundcite ask` against
    far-25 with the real LLM, output pasted in the commit message.

### Phase 5 — EvalService full pipeline + persistence + report
11. `EvalService.run_full(suite, judge: bool)`: per case run `ask()`
    (non-streamed collection), score citation_precision + abstention
    correctness (hand-rolled), faithfulness via the ragas judge adapter when
    `--judge` (AD-7); persist per AD-6; extend the report file with the new
    columns; implement `groundcite eval report <run-id>`.
    → **verify:** unit tests with FakeLLM + FakeRepository (a must-abstain case
    that abstains scores correct; one that answers scores incorrect; citation
    precision arithmetic golden-numbered). Judge path: one paid smoke run on
    ≤3 cases first to sanity-check cost/latency BEFORE the full suite.

### Phase 6 — First full baseline + τ tuning (the deliverable)
12. Run the FULL baseline honestly at spec defaults (τ=0.35, rerank on):
    core + german + negative, `--judge` if a judge key exists. Commit the
    report: `eval: first full-pipeline baseline` with the complete table —
    including the 25% negative-suite leak. The bad number IS the story (§8
    honesty rule).
13. τ sweep from the run's recorded top-scores (no re-asking needed): table of
    τ ∈ {0.35, 0.5, 0.6, 0.65, 0.70, 0.75} × (grounded wrongly-abstained %,
    must-abstain leak %). Pick zero-leak τ (expect ≈0.70). ONE commit: new
    `TAU_RETRIEVAL` default in config + `.env.example` + spec §7 default line +
    removal of the dead "RRF ≥ 0.05" clause (AD-3) + before/after eval tables
    (rule 4 + spec preamble).
14. Re-run the full suite at the tuned τ; commit the after-report.
    → **verify:** negative-suite leak = 0/12 at tuned τ; grounded abstention
    cost stated plainly; recall metrics unchanged (τ does not touch ranking).

### Phase 7 — Baseline artifact + close-out
15. `evals/baseline.json` + `scripts/check_baseline.py` (AD-8; CI wiring
    explicitly deferred with reason in the commit).
16. Full gates: ruff + ruff format + mypy --strict + import-linter + pytest
    (unit AND integration with live DB). Push; confirm CI green; update
    `docs/WEEK2_PLAN.md`-style results section in a `docs/WEEK3_RESULTS.md`
    (final tables, decisions taken, residuals for Week 4).

---

## 5. Explicitly OUT of scope (do not touch)

- FastAPI app, SSE endpoint, `sse-starlette` (Week 4 — but note `AskEvent` is
  already SSE-shaped; do not invent a second event type).
- Web UI (Week 5). New corpora / re-ingestion (corpus is clean; chunking
  changes would invalidate all Week-3 baselines — forbidden this week).
- `tsv_de`, qdrant, multi-tenant anything (§16).
- `evals/suites/*` edits of any kind (rule 13 — owner-only).
- CI database service container / corpus fixtures (Week-4 decision).

## 6. Environment facts (save yourself the rediscovery)

- Windows 11; PowerShell 5.1 primary (no `&&`; beware `2>&1` on native exes);
  Git Bash available. Venv: `core\.venv\Scripts\python.exe` (+ `uv` on PATH;
  run tooling from `core/`).
- Postgres 16 + pgvector via docker compose, host port **5433**, container
  `groundcite-db`. Docker Desktop may be DOWN after a laptop sleep — start it
  and wait for the health check before blaming your code.
- Unit tests: `python -m pytest tests -q --ignore=tests/integration` (fast).
  Integration tests auto-skip without the DB. Full ingest ≈ 35 min CPU — you
  should NOT need it (no chunking changes allowed).
- Long-running work (evals with judge, anything >10 min): run detached, log to
  files, poll the DB/file for completion — sessions can drop mid-run. The
  reranked full-suite eval costs ~25 min CPU; budget for it.
- Known tooling quirks already solved — copy the patterns, don't rediscover:
  typer + ruff B008 (`extend-immutable-calls`), mypy strict + optional-dep
  adapters (per-module override block), reranker logits need sigmoid (done),
  eval suites' `##`-prefixed draft lines are skipped by the loader.

## 7. Evidence bar (how your work gets accepted)

Every commit that changes pipeline behavior carries, in its message: the
command(s) run, the before/after eval table (or the relevant real transcript
for adapters), and any residual honestly stated. A claim without pasted output
does not merge. When something is worse than expected, the number still gets
committed — the improvement narrative needs the honest starting point (§8).
