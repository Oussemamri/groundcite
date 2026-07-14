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
| `rerankers` | the Reranker port wraps it (§11 table) | **explicitly allowed** |

**Exactly one** new dependency, in an optional extra (`[rerank]`), lazily
imported, so CI stays dependency-free.
**No RAG framework. No LangChain/LlamaIndex/Haystack** (rule 11).

**`pgvector-python` considered and rejected.** It is on the §11.1 allow-list, but
the allow-list is permission, not obligation: `pg_repo` already writes embeddings
with a zero-dependency pgvector text literal (`_embedding_literal`), and the
dense query needs only the same representation plus a `::vector` cast. Adding a
library to duplicate a working helper fails rule 0 (simplicity, match existing
style) and buys nothing. The dense adapter reuses the same literal format.

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

### Phase 6 — First real baseline  ✅ DECIDED: pull forward (spec §15.1 amendment)
12. Hand-rolled `recall@5`, `recall@10`, `MRR` (spec §8: ~15 lines each, no library,
    no judge, no LLM) over the existing 99-case golden set.
13. `groundcite eval run --suite core --retrieval-only` → scored table + `evals/reports/<sha>.md`.
    → **verify:** a real recall@5 number on 71 core cases, committed honestly
      (§8 honesty rule), reranker-off and reranker-on.

### Phase 7 — Gates
14. ruff + mypy --strict + import-linter + pytest green locally and on `origin/main`.
15. Conventional commits, one feature per commit (rule 7).

---

## 3. Decision (settled) — retrieval evals pull forward into Week 2

**DECIDED: yes.** Recorded as the **§15.1 amendment** in the spec, so code and
spec do not silently drift (spec preamble: "if code and spec disagree, fix one
of them in the same PR").

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

It is not a reorder so much as splitting §8 along a seam the spec itself already
draws ("retrieval-only smoke cases (no judge) are the most stable CI signal").
The judge half (faithfulness, Ragas, generation, Gates A/B) stays in Week 3.

## 3b. RESULTS (filled in as built)

**First baseline** — far-25, reranker OFF, sha `695a2ef`:

| suite | scored cases | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| core | 40 | **0.769** | **0.844** | **0.811** |
| german | 8 | 0.917 | 0.917 | 0.938 |
| negative | 10 (must-abstain) | — | — | — |

German outscores English because clause numbers survive translation and fire the
exact-match fast path; multilingual bge-m3 carries the rest. This is the honest
starting number (spec §8 honesty rule) — the blog narrative is the improvement.

**Reranker ON vs OFF** (far-25; the `+rerank` tuning step of spec §15, measured
per CLAUDE.md rule 4):

| suite | metric | rerank OFF | rerank ON | Δ |
|---|---|---|---|---|
| core | recall@5 | 0.769 | **0.856** | **+8.7 pts** |
| core | recall@10 | 0.844 | **0.896** | +5.2 pts |
| core | MRR | 0.811 | **0.824** | +1.3 pts |
| german | recall@5 | 0.917 | 0.917 | — |
| german | MRR | 0.938 | 0.938 | — |

The cross-encoder earns its cost on the English suite. German is unchanged
because those cases are already solved at rank 1 by the clause fast path, which
the reranker cannot improve on.

### FINDING — Gate A cannot be built on RRF (blocks Week 3)

The eval harness earned its place immediately. Measured on the fused scale:

- Fused top-scores collapse to **1/61 = 0.0164** for nearly every case (the top
  chunk is usually rank-1 in only ONE of the two lists).
- Grounded and must-abstain cases have **identical** min/median top-scores, and
  **25 of 40** grounded cases score at or below the *best* must-abstain case.
- Spec §7's reranker-off gate, "RRF ≥ 0.05", is therefore **unreachable** (the
  two-list ceiling is 2/61 = 0.0328) **and useless** (the distributions overlap
  completely).

Visible in the DoD sample: the out-of-corpus question ("What does DO-178C say
about MC/DC?") tops out at 0.0164 — the *same score* as legitimate hits for cabin
pressure, fire detection, and bird strike.

**⇒ The reranker is REQUIRED for Gate A, not optional.** Week 3 must either make
the reranker mandatory or replace the RRF threshold with a calibrated score.
Pinned by a unit test so the arithmetic cannot silently drift.

**The reranker largely fixes it — but Gate A still leaks.** Same measurement on
normalized cross-encoder scores (48 grounded cases, 12 must-abstain):

| | grounded (n=48) | must-abstain (n=12) |
|---|---|---|
| min | 0.1364 | 0.0015 |
| **median** | **0.9485** | **0.0483** |
| max | 0.9995 | 0.7220 |

A ~20× median gap, versus the RRF scale where the two were *identical*. But the
tails still overlap (7/48 grounded score at or below the best must-abstain case),
so **no τ separates them perfectly**. At the spec's `TAU_RETRIEVAL = 0.35`:

- **2/48 grounded** cases would be wrongly ABSTAINED (4%) — acceptable.
- **3/12 must-abstain** cases would be wrongly ANSWERED (**25%**) — *not*
  acceptable. GroundCite's core contract (§1) is that it abstains rather than
  cite wrongly, and a quarter of out-of-corpus questions currently slip through.

Week 3 must tune τ against this distribution (and likely add Gate B's citation
check as the second line of defence, which is exactly what §7 designs it for).
τ = 0.35 is a plausible starting point but is NOT safe as-is.

### Known residual, as predicted (AD-5) — FIXED post-Week-2

The §25.1801 catch-all, the page-furniture pollution, and (found while building
the golden-set verification worksheet) a print-hyphenation bug affecting 90% of
chunks were all fixed and re-ingested. Full before/after:

| | original | +appendix/noise fix | **+de-hyphenation (final)** |
|---|---|---|---|
| core recall@5 (rerank OFF) | 0.769 | 0.781 | **0.800** |
| core recall@10 (rerank OFF) | 0.844 | 0.844 | **0.879** |
| core MRR (rerank OFF) | 0.811 | 0.811 | **0.853** |
| core recall@5 (rerank ON) | 0.856 | — | **0.863** |
| core recall@10 (rerank ON) | 0.896 | — | **0.902** |
| core MRR (rerank ON) | 0.824 | — | **0.850** |
| german recall@10 (rerank OFF) | 0.917 | 0.917 | **0.958** |

The reranker-OFF number moved the most (+3.1 recall@5, +4.2 MRR) — de-hyphenation
repairs lexical retrieval directly (`websearch_to_tsquery` can only match whole
words, and "seconds" had been stored as the tokens "sec" and "onds"). The
reranker-ON gain is smaller in absolute terms because the cross-encoder was
already compensating for some of the corpus damage by reading full passages
rather than relying on exact tokens.

The §25.1309 "catastrophic failure probability" miss present after the appendix
fix alone is gone post-de-hyphenation; only one core miss remains
(§25.301/303 — a genuine question/clause vocabulary mismatch, not a corpus defect).

Gate A separability improved but is NOT resolved: with the reranker on,
overlapping cases dropped 7/48 → 5/48, but at τ=0.35 the must-abstain leak rate
is unchanged (3/12 = 25%). This confirms the leak is a reranker-calibration /
Gate-B problem, not a corpus-quality problem — correctly Week 3's to solve.

Golden-set verification worksheet (`scripts/verify_golden_set.py`) run against
the final corpus: 2/48 scorable cases flagged, both manually reviewed against
the full ingested text and confirmed FALSE POSITIVES (stemming mismatches —
"demonstrated" vs "demonstration" — not missing content). Zero MISSING clauses
across all 60 committed cases.

## 4. Explicitly OUT of scope for Week 2

- Generation / the LLM answerer (`llm/*` adapters stay stubs) — Week 3.
- Gate A (τ_retrieval) and Gate B (citation validity) — Week 3.
- LLM-judge metrics, faithfulness, Ragas — Week 3.
- FastAPI, SSE, web UI — Weeks 4–5.
- `tsv_de` German lexical column — spec §16 extension, not v1.
- Fixing the §25.1801 SFAR/appendix chunking residual — separate authorized task.
