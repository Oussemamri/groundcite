# Week 2 — Hybrid retrieval + fusion + `groundcite ask` (retrieval-only)

> Spec: §7 (ask pipeline), §11 (tech choices), §15 (milestone).
> **DoD (spec §15):** "top-6 chunks printed with scores for 10 sample questions."
> Working style: CLAUDE.md rule 0 — every step below carries a `verify:` line.

## 0. Where we actually are

Week 1 closed: FAR-25 ingested (3336 sections, 1712 chunks, real 1024-d bge-m3
embeddings), clause tree correct, breadcrumbs correct.

Three facts that shape this plan, verified in the repo (not assumed):

1. **The Week-2 ports already exist and are correct** — `VectorIndex`,
   `LexicalIndex`, `Reranker`, `LLMProvider` in `ports/protocols.py`. Week 2
   fills stubs behind stable seams; it does not design new seams.
   Every adapter it needs is a 4–5 line stub today.
2. **The schema is already retrieval-ready** — `chunks.embedding vector(1024)`,
   HNSW cosine index, `tsv` generated column, GIN index, `chunks_clause_idx`.
   No migration needed.
3. **The golden set already exists** — 99 human-verified cases committed
   (71 core / 13 german / 15 negative), exceeding the spec's ≥60 target. P2 is
   done. This is what makes §6 below possible.

The retrieval tunables are *already* in `config.py` (`tau_retrieval`, `rrf_k`,
`candidates_dense`, `candidates_lexical`, `fused_k`, `context_k`) — Week 2 adds
almost no new config.

## 1. Architectural decisions

### AD-1 — `retrieve()` is a first-class, LLM-free entry point on `AskService`

Spec §7 defines `AskService.ask()` as a *stream of AskEvents* that includes
generation. Week 2 must produce retrieval **without** an LLM. Rather than
half-building `ask()`, we add:

```python
class AskService:
    def retrieve(self, question: str, filters: AskFilters | None) -> RetrievalResult: ...
    def ask(self, ...) -> Iterator[AskEvent]: ...   # Week 3; calls retrieve() internally
```

**Why a method, not a 5th `RetrievalService`:** spec §4 fixes the service
inventory at four (Ingestion/Ask/Eval/Library). A new service is a spec change;
a method is not.

**Why it must be LLM-free:** spec §8 requires recall@k / MRR metrics *and*
states "retrieval-only smoke cases (no judge) are the most stable CI signal."
Week 3's `EvalService` therefore needs to call retrieval **without** touching a
generator. Confirmed legal: import-linter forbids `services → adapters/config`,
but permits service→service, so `EvalService` may consume `AskService.retrieve`.

This is the single most important structural call in Week 2: it is what makes
the eval harness (the project's actual differentiator, §1) buildable at all.

### AD-2 — Fusion and clause-detection are OURS, as pure functions

`services/fusion.py` (new): RRF `score(c) = Σ 1/(rrf_k + rank_i(c))`, clause
fast-path injection at rank 1, top-`fused_k` cut.
`services/clause_detect.py` (new): the §7 step-0 regexes.

Pure, dependency-free, exhaustively unit-testable with no DB and no fakes.
Spec §11.1 lists "hybrid fusion (RRF) + clause fast-path" under **Build (ours,
always)** — this is the portfolio piece; no library touches it.

### AD-3 — Build the reranker, but baseline WITHOUT it first

The `bge_reranker` adapter gets built in Week 2 (it is §7 step 3 and the port
exists), but the **first baseline is measured reranker-off**. Spec §8's honesty
rule is explicit: "the blog post narrative is the *improvement*, which requires
committing the bad baseline." Turning the reranker on then becomes a *measured*
change in Week 3 (`+rerank` in §15's tuning sequence), with a before/after table
— which is exactly what CLAUDE.md rule 4 demands.

No spec conflict: `RERANKER_ENABLED` keeps its spec default; we simply record
both numbers.

### AD-4 — German is a known-weak spot we MEASURE, not fix

Dense (bge-m3, multilingual) handles German questions over the English corpus.
Lexical `websearch_to_tsquery('english', …)` will do poorly on them. That is
**expected and in-scope to measure** — the `tsv_de` column is a spec §5/§16
extension, explicitly not v1 Week 2. The German suite exists precisely to expose
this. We report the number; we do not build `tsv_de` now.

### AD-5 — Known Week-1 residual that will show up here

§25.1801 (SFAR/Appendices) holds 84 oversized chunks because that text carries
no `§`-style headers. Retrieval on appendix/SFAR questions will be visibly worse.
Expect it in the eval breakdown; do not silently "fix" it inside Week 2.

### New dependencies (rule 11 allow-list, rule 12 pin everything)

| Lib | Why | Rule-11 status |
|---|---|---|
| `pgvector` | psycopg vector type registration; steal its hybrid-search SQL shapes (§11.1) | **explicitly allowed** |
| `rerankers` | the Reranker port wraps it (§11 table) | **explicitly allowed** |

Both go in optional extras (`[rerank]`), lazily imported, so CI stays dependency-free.
**No RAG framework. No LangChain/LlamaIndex/Haystack** (rule 11).

---

## 2. Phase plan

### Phase 0 — Dependencies & config
1. Add `pgvector` to core deps (pinned); add `[rerank]` extra with `rerankers` (pinned).
   → **verify:** `uv sync --frozen` clean; `uv run lint-imports` still 5/5.
2. Add `reranker_model: str = "BAAI/bge-reranker-v2-m3"` to `config.py` + `.env.example`
   (rule 9: model names live in config defaults only).
   → **verify:** `get_settings()` round-trips; no model name string anywhere outside config.

### Phase 1 — Retrieval adapters (the two SQL shapes)
3. `adapters/lexical/pg_lexical.py` — `PgLexicalIndex`:
   - `search()`: `ts_rank_cd(tsv, websearch_to_tsquery('english', %s))` ORDER BY rank DESC LIMIT k,
     optional `document_slugs` filter.
   - `match_clause()`: exact `clause_path` equality (uses `chunks_clause_idx`).
   → **verify:** integration test vs compose Postgres — a known FAR phrase returns
     its known clause in the top-5; `match_clause('14 CFR Part 25 §25.1309')` returns rows.
4. `adapters/vector/pg_vector.py` — `PgVectorIndex.search()`:
   cosine via `embedding <=> %s::vector`, score = `1 - distance`, HNSW, slug filter.
   → **verify:** integration test — embedding a chunk's own text retrieves that chunk
     at rank 1 with score ≈ 1.0 (self-retrieval sanity).

### Phase 2 — The parts that are ours (pure, no I/O)
5. `services/clause_detect.py` — spec §7 step 0 regexes (`\b\d+(\.\d+)+[a-z]?\b`,
   `§ 25.1309`, `ECSS-…`) → normalized `clause_path` candidates.
   → **verify:** unit tests — "What does §25.1309(b) require?" → `25.1309(b)`;
     prose with no clause → none. Table-driven, no DB.
6. `services/fusion.py` — RRF over N ranked lists + clause fast-path at rank 1 + top-k cut.
   → **verify:** unit test with hand-computed RRF scores (golden numbers, not
     approximations); a chunk hit by both lists must outrank one hit by either alone;
     a fast-path clause hit lands at rank 1.

### Phase 3 — Orchestration
7. `AskService.retrieve()` — dense ∥ lexical ∥ (clause fast-path) → RRF → top-`fused_k`
   → optional rerank → top-`context_k`; returns `RetrievalResult` carrying the ranked
   `RetrievedChunk`s **and** `pipeline_debug` (per-stage timings + pre/post-fusion
   candidate scores, spec §12).
8. Fakes: `FakeVectorIndex`, `FakeLexicalIndex`, `FakeReranker` in `tests/fakes.py`.
   → **verify (rule 3):** unit tests with fakes only — no DB, no network. Cover:
     dense-only hit, lexical-only hit, both-hit ordering, clause fast-path injection,
     `document_slugs` filter, reranker on vs off.

### Phase 4 — Reranker adapter
9. `adapters/reranker/bge_reranker.py` wrapping `rerankers` (normalize=True so scores
   feed τ_retrieval per §11), lazy import, `RERANKER_ENABLED` honored.
   → **verify:** contract test with a tiny candidate list; reordering is stable and
     scores ∈ [0,1]. Skipped when the extra isn't installed (CI path).

### Phase 5 — CLI + wiring
10. `container.build_services` wires `PgVectorIndex`/`PgLexicalIndex`/reranker into `AskService`.
11. `groundcite ask "…" [--json] [--slug far-25] [--top-k 6]` → retrieval-only table:
    rank, score, clause_path, snippet.
    → **verify (DoD):** run 10 sample questions, paste the top-6 tables. This is the
      spec §15 Week-2 proof.

### Phase 6 — First real baseline  ⚠️ NEEDS YOUR DECISION (see §3)
12. Hand-rolled `recall@5`, `recall@10`, `MRR` (spec §8: ~15 lines each, no library,
    no judge, no LLM) over the existing 99-case golden set.
13. `groundcite eval run --suite core --retrieval-only` → scored table + `evals/reports/<sha>.md`.
    → **verify:** a real recall@5 number on 71 core cases, committed honestly
      (§8 honesty rule), reranker-off and reranker-on.

### Phase 7 — Gates
14. ruff + mypy --strict + import-linter + pytest green locally and on `origin/main`.
15. Conventional commits, one feature per commit (rule 7).

---

## 3. The one decision I need from you

**Do we pull retrieval-only eval metrics (Phase 6) into Week 2?**

Spec §15 puts the eval harness in Week 3 and says "resist reordering" — so this
is a real deviation and I won't do it silently (rule 1).

**The case for pulling it forward:** Week 2 *builds retrieval and fusion*, and
CLAUDE.md rule 4 says every change to retrieval/fusion/thresholds must ship with
an eval run. Without Phase 6, Week 2's entire quality bar is "eyeball 10
questions" — and every tuning decision in Week 3 would be retro-justified. The
metrics needed are recall@k and MRR: pure arithmetic over `expected_clauses`,
**no judge, no LLM, no Ragas, no new dependency** — they are the cheap half of
§8. The expensive half (faithfulness / LLM-judge / Ragas / generation) stays in
Week 3 where the spec puts it.

**Cost:** roughly half a day, and it front-loads `EvalService` scaffolding.
**Benefit:** Week 2 ends with "recall@5 = 0.XX on 71 real cases" instead of a
vibe check — which is the project's stated differentiator (§1) and the honest
bad baseline the blog post needs (§8).

**My recommendation: pull it forward.** It is not a reorder so much as splitting
§8 along a seam the spec itself already draws ("retrieval-only smoke cases (no
judge) are the most stable CI signal").

## 4. Explicitly OUT of scope for Week 2

- Generation / the LLM answerer (`llm/*` adapters stay stubs) — Week 3.
- Gate A (τ_retrieval) and Gate B (citation validity) — Week 3.
- LLM-judge metrics, faithfulness, Ragas — Week 3.
- FastAPI, SSE, web UI — Weeks 4–5.
- `tsv_de` German lexical column — spec §16 extension, not v1.
- Fixing the §25.1801 SFAR/appendix chunking residual — separate authorized task.
