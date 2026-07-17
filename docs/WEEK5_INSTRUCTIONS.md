# Week 5 — the `/evals` page, abstention polish, README + demo, blog draft: execution instructions

> Audience: the AI engineer (model) executing Week 5. Read this WHOLE file, then
> `GROUNDCITE_PROJECT_SPEC.md` (§2.2, §8, §10, §11, §15) and `CLAUDE.md`, before
> writing any code. Where this file says "DECIDED", the architecture call has
> already been made with the repo owner — implement it, do not re-litigate it.
>
> Deliverable (spec §15 Week 5): **the `/evals` page (runs table + per-suite
> metric chart + per-case drill-down — the screenshot for the blog post),
> abstention polish, a README benchmark table with the real numbers, a demo
> capture, and a DRAFTED blog post.** This is the LAST feature milestone.
> Spec §15 scope armor: **after Week 5, only bugfixes + the blog post — new
> ideas go to `docs/ROADMAP.md`, not to code.**
>
> Three things in this week's spec row are the OWNER's to do, never the model's
> (outward-facing, hard to reverse): **making the repo public, publishing the
> blog post, and putting the link on a CV.** The model drafts and captures; the
> owner ships. This file marks those `OWNER ACTION` and stops at the draft.

---

## 0. Non-negotiable rules (violations = rejected work)

1. **Read the spec first** (CLAUDE.md rule 1). If a task here conflicts with the
   spec, stop and say so — except where this file records a spec amendment
   (spec preamble: when code and spec disagree, fix one of them in the same PR).
2. **Dependency rule is law** (rule 2): domain ← ports ← services/adapters ←
   apps. The one backend change this week (Phase 1) is a Repository read
   extension — port + `pg_repo` + `FakeRepository` in lockstep, exactly the
   Week-4 AD-4 discipline. import-linter's 5 contracts run before every commit.
3. **Every service-layer change ships with unit tests using fake ports**
   (rule 3). The Phase 1 read gets fake-port unit tests first, then a live-DB
   integration check against the 13 real eval runs already persisted.
4. **Rule 4 (eval run per retrieval/fusion/threshold/prompt change) MUST NOT
   trigger this week.** Week 5 adds a read-only page + polish + docs over the
   FROZEN Week-3 eval data. If you find yourself editing chunking, retrieval,
   fusion, thresholds, prompts, OR the eval writer/scorer (`services/eval.py`'s
   `run_full`/`run_retrieval`), STOP — that is scope creep. The `/evals` page
   reads what is ALREADY persisted; it never re-runs a suite to get prettier
   data (that spends Groq tokens and would change the numbers the blog commits
   to). Reading `evals/baseline.json` and `evals/reports/*.md` is fine.
5. **mypy --strict on core; no `Any` in ports** (rule 5). `apps/api` runs mypy on
   `app tests` together (the Week-3/4 lesson: `mypy app` alone misses test gaps).
6. **TypeScript rules** (rule 6): TS strict, **no `any`**, TanStack Query for ALL
   server state (the `/evals` reads are pure `useQuery` — no manual `useEffect`
   fetching). Response-model TS mirrors change in the SAME commit as the Python.
7. **Build-vs-buy** (rule 11 / spec §11.1): charting is **Buy** — spec §10 names
   `recharts` explicitly (AD-4). It is NOT yet on the CLAUDE.md allow-list, so it
   gets a spec §11 table row FIRST, same commit as first use (rule 11), pinned
   `==`/exact. NEVER add LangChain/LlamaIndex/Haystack; on the web side still no
   axios/swr, no component library — Tailwind + fetch + TanStack Query + the one
   charting lib.
8. **Pin every dependency version** (rule 12): `recharts` pinned exact in
   `package.json`; `package-lock.json` re-committed. Judge model name stays in
   config, snapshotted into every eval run (unchanged — no new eval runs here).
9. **NEVER create or modify anything under `evals/suites/`** (rule 13). Reading
   `evals/baseline.json` and `evals/reports/` is allowed; writing them is not
   part of this week (they're already committed from Week 3).
10. **Domain language** (rule 8 / spec §2.1): Suite, Case, Run, Result,
    GROUNDED/ABSTAINED, recall@k, MRR, citation precision, abstention accuracy —
    in API paths, response models, UI copy, chart labels, and the blog. §2.2
    copy rules hold on the abstention polish: title exactly "No grounded
    answer", never cute.
11. **Small diffs, one feature per commit, conventional commits** (rule 7).
    `feat:` for the page/polish, `docs:` for README/blog/results. The web app
    still gets NO secrets — it talks only to the API.
12. **Honesty rule is the whole point of this week** (spec §8): "README
    benchmark table shows current real numbers, including the embarrassing
    first baseline. The blog post narrative is the *improvement*, which requires
    committing the bad baseline." Every number on the `/evals` page, in the
    README table, and in the blog comes from persisted data or a committed
    report — verified, never recalled or rounded to look better. If the
    headline improvement you expected isn't in the data, retitle to the one
    that IS (see AD-7).

**Working style** (rule 0): diagnose with evidence before coding; state
assumptions; boring beats clever; surgical diffs; browser-verify every web
change against a real running server (CLAUDE.md), never "it type-checks".

---

## 1. Where the project stands (verified facts, 2026-07-16)

Weeks 0–4 done and pushed; CI green on `main` (3 jobs: core+db, api, web) at
`e556024`. `docs/WEEK4_RESULTS.md` is the honest record.

**Working today, relevant to this week:**
- Eval read routes exist and are unit- + integration-tested:
  `GET /api/v1/eval/runs` (list, newest first), `GET /api/v1/eval/runs/{id}`
  (run + per-case results), `POST /api/v1/eval/runs` (trigger, AD-5 — NOT used
  by this page; the page is read-only).
- `lib/api.ts` already has `listEvalRuns()`, `getEvalRun()`, `triggerEvalRun()`,
  `getJob()` and the `EvalRunOut`/`EvalResultOut`/`EvalRunDetailOut` TS mirrors.
- `/ask` abstention already works end-to-end (Week 4 Phase 7, browser-verified):
  `AbstentionCard` with exact §2.2 copy, closest-passage cards, GENERATING
  correctly dim, costs zero Groq tokens (Gate A blocks pre-LLM).
- `/evals` is a labeled Week-5 shell (`app/evals/page.tsx`), Nav already links it.
- `evals/baseline.json` (sha `19de5cd`, τ=0.70, gpt-oss-120b) holds the current
  headline numbers; `evals/reports/*.md` holds per-sha per-suite reports
  (`0207360-*`, `24a5241-*`, `473cdd3-*`) — the raw material for a trend/history.

**The eval DATA that the `/evals` page reads (verified against the live DB — 13
runs persisted):**
- `eval_runs`: `id`, `git_sha`, `config` (jsonb — `tau_retrieval`/`groq_model`/
  `llm_provider` present on FULL runs; retrieval params on all), `started_at`.
  There are 13 runs: 4 git_shas × 3 suites (core=40, german=10, negative=10),
  plus one 1-result stray. **Only FULL-pipeline runs are persisted** —
  retrieval-only runs are not (`services/eval.py` + spec §15.1). So the page's
  recall/MRR come from the per-case rows of FULL runs (which DO store them).
- `eval_results`: `run_id`, `case_id`, `recall_at_5`, `recall_at_10`, `mrr`,
  `citation_precision`, `faithfulness` (null — no judge run), `abstained`,
  `passed`, `debug` jsonb = `{ask_id, status, top_score, latency_ms,
  cited_clauses[], error_message}`.
- `eval_cases`: `id`, `suite`, `question`, `expected_clauses[]`,
  `expected_facts[]`, `must_abstain`, `language`.

**The read GAP this week fills (verified — this is the ONLY backend work):**
The current API run detail returns per-case `case_id` (a UUID) + metrics + debug,
but **NOT** the case's `question`, `expected_clauses`, `suite`, or `must_abstain`
— those live in `eval_cases` and are never joined. The `EvalRun` domain type has
**no `started_at` and no `suite`** either. The `/evals` per-case drill-down
("retrieved-vs-expected clauses", spec §10) and the runs table (suite label,
date) cannot be built without exposing that case metadata. Repository has
`get_eval_run`, `get_eval_results`, `list_eval_runs` — but **no read for
`eval_cases`**. Phase 1 adds it (AD-2), same lockstep discipline as Week 4 AD-4.

**What is NOT persisted, and therefore honestly cannot be shown** (drives AD-3):
the literal ranked *retrieved* clause list per case. FULL runs store the recall@k
NUMBERS and the answer's `cited_clauses`, but not the top-k retrieved clause_ids;
retrieval-only runs (which DO compute `retrieved_clauses`) aren't persisted at
all. Recovering the literal retrieved list means either a re-run or an eval-writer
change — both forbidden this week (rule 4). The drill-down shows what IS stored.

**The blog-honesty landmine (verified, address it head-on):** `baseline.json`
recall@5 core = 0.863, and `docs/WEEK3_RESULTS.md` states this is "identical to
Week 2's final numbers" — recall@5 did **not** dramatically improve across the
tracked history. The spec's suggested blog title "Recall@5 from X→Y on FAR Part
25" may have **no real X→Y delta** to stand on. The improvement that IS
dramatic and documented is the τ-tuning zero-leak result (must-abstain leak
25.0% → 0.0%, `WEEK3_RESULTS.md` Phase 6) and citation precision. AD-7 handles
this: verify the real delta from committed reports FIRST, then title the post
after the improvement that actually exists.

---

## 2. Look-outside survey (done — verdicts binding per rule 11)

| Candidate | Verdict | Why |
|---|---|---|
| **`recharts`** | **ADOPT** (pinned, apps/web dep) — DECIDED, no fallback | Spec §10 names it explicitly for the `/evals` chart; §11.1 puts charting under Buy (not a portfolio algorithm). Gets a spec §11 row first (rule 11). Owner confirmed this over hand-rolled SVG: this page is the blog screenshot, and recharts' axis/tooltip/legend/responsive polish earns the one new dependency. See AD-4 for the honest-visualization constraint. |
| hand-rolled SVG chart | reject | Genuinely viable given the tiny dataset (~4 shas) — considered and explicitly passed over in favor of recharts (owner decision, see above). Not a fallback; do not switch to this without a new owner decision. |
| `chart.js` / `nivo` / `visx` / `d3` direct | reject | Spec names recharts specifically; no reason to diverge. One charting lib, spec-chosen. |
| `@tanstack/react-table` | reject | The runs table is a handful of rows; plain `<table>` + Tailwind (same as `/library`) is enough. No new dep. |
| **Playwright video capture** (already in scratchpad) | **ADOPT** (tooling only, not a project dep) | For the demo capture (AD-6). Already installed in the scratchpad from Week 4; `page.video()` records webm. NOT a project dependency. GIF conversion is a local tooling step, flagged for the owner if `ffmpeg`/`gifski` isn't present. |
| a hosted analytics/telemetry lib for the page | reject | The page reads our own eval API; no third-party anything. |

**Version rule (spec §11 last row):** verify `recharts`'s current version at
build time and pin exact (`==`-equivalent in `package.json`, no `^`). Re-commit
`package-lock.json`.

---

## 3. Architecture decisions (DECIDED — implement, don't re-litigate)

**AD-1 — `/evals` reads persisted FULL-pipeline runs only.** Retrieval-only runs
are not persisted (spec §15.1). The recall@5/@10/MRR the page shows come from the
per-case rows of FULL runs (they store those columns). State this in the page's
top-of-file docstring so nobody later "wonders where the retrieval-only trend
is" — there isn't one by design. The page never triggers a run (`POST
/eval/runs` exists but is out of scope here; the page is strictly read-only).

**AD-2 — Backend read extension (the only core/API work; port + `pg_repo` +
`FakeRepository` in lockstep, one commit, Week-4 AD-4 discipline):**
- Add a Repository read for eval-case metadata keyed by case id — e.g.
  `get_eval_cases(case_ids: list[UUID]) -> dict[UUID, Case]` (or
  `list_cases_for_run(run_id)`; pick the shape that keeps the route thin).
  Returns `question`, `expected_clauses`, `suite`, `must_abstain`, `language`.
  **First check for an existing domain type** for a case; if none, add a frozen
  `Case` model in `domain/` (spec §2.1 name — "Case", never "test"/"example").
- Expose `started_at` (and the derived `suite`) on the run read. `EvalRun`
  domain currently lacks `started_at`; add it (it's a real column, harmless to
  surface, and the runs table wants recency/order). `suite` is derivable by
  joining the run's cases (all cases in one run share a suite) — expose it once,
  don't make the frontend re-derive it.
- Extend the API run-detail response so each per-case result carries the case
  metadata alongside its metrics: `{question, expected_clauses, must_abstain,
  language, cited_clauses, recall_at_5, recall_at_10, mrr, citation_precision,
  abstained, passed, status, top_score, latency_ms}`. Map EXPLICITLY from domain
  objects (AD-6 from Week 4 — never `model_dump()` a domain entity).
- Aggregates (per-run abstention accuracy, mean citation precision, recall@5)
  are computed from the persisted per-case rows — **in the service/route from
  stored data**, NEVER by re-running. No `eval_runs` schema column is added.
- Unit tests with `FakeRepository` first (rule 3): case join returns the right
  metadata, unknown case id handled, aggregates match a hand-computed fixture.
  Then a live-DB integration check: `GET /eval/runs` lists 13, a real run's
  detail carries `question`/`expected_clauses` for its cases.

**AD-3 — The drill-down shows EXPECTED vs CITED clauses + the stored numbers,
not a literal retrieved top-k.** Persisted FULL-run data gives us
`expected_clauses` (from the case), `cited_clauses` (what the answer cited, from
debug), and the numeric `recall_at_5/@10`, `mrr`, `citation_precision`,
`abstained`, `passed`. The drill-down renders: expected clauses, cited clauses
with hit/miss highlight against expected, the metric numbers, and abstention
correctness (`must_abstain` vs `abstained`). This is the honest reading of spec
§10's "retrieved-vs-expected" over the data that exists — the recall NUMBER is
the retrieval signal; the CITED list is the generation signal. Do **not** invent
a retrieved list, and do **not** re-run to get one (rule 4). If the owner later
wants the literal ranked retrieved clauses on this page, that is a Week-6+
eval-writer change (store `retrieved_clauses` in per-case debug) + a re-run —
explicitly out of scope, noted in `WEEK5_RESULTS.md` residuals.

**AD-4 — Charting is `recharts`, and the chart tells the truth about a small,
mixed-config dataset.** Add the spec §11 row (charting, Buy, recharts) in the
same commit as first use. The dataset is thin (4 git_shas, and configs differ
across them — τ=0.35 vs 0.70, model swaps). A cross-config time-series LINE that
connects incomparable points would be dishonest. So the chart's default view is
a **per-suite grouped bar of the current baseline's three headline metrics**
(abstention accuracy, mean citation precision, recall@5) for the latest
comparable run — clear, honest, and the strong blog screenshot. Where multiple
runs share a config, the same component may show them as an ordered series
keyed on `git_sha` (categorical x-axis), labeled with the config so the reader
knows what changed. Mono font on all clause IDs / scores / shas (spec §2.2
signature detail) carries onto axis ticks and tooltips. `recharts` is the
library — owner-confirmed, not open for re-litigation (see §2 survey); the
honesty constraint on WHAT the chart shows is equally DECIDED, not a style
preference either.

**AD-5 — Abstention polish is surgical, not a rebuild.** `/ask` abstention
already works; polish means (a) surface the `AbstentionReason`
(`weak_retrieval` vs `uncited`) in calm §2.2 tone so the user sees *why* it
abstained, not just that it did; (b) make the closest-passage cards link into
the reader like citation cards do — they carry `chunk_id` + `clause_path`, so
the same deep-link that Week-4 Phase-8 wired for citations applies (closes a
Week-4 residual naturally, no new mechanism); (c) audit that abstention reads as
a first-class result, never an error (amber, not red; the passages framed as
"here's the closest I found", per §2.2). Keep the title exactly "No grounded
answer". No pipeline/threshold change (rule 4).

**AD-6 — README benchmark table + demo capture, real numbers only.** The README
gets the spec §8 benchmark table straight from `evals/baseline.json` (current
real numbers, all three suites, including `negative`'s structural 0.0 recall and
the honest abstention-accuracy story) — and it must include the embarrassing
FIRST baseline for contrast (the τ=0.35 numbers from `WEEK3_RESULTS.md` Phase 6,
which are committed). Demo capture: drive the real running app with the
scratchpad Playwright and record `page.video()` (webm) of the full §15 loop (ask
→ grounded stream → click citation → reader highlight → one abstention → the
`/evals` page). Convert to GIF only if `ffmpeg`/`gifski` is available locally;
if not, deliver the webm + key frames and flag the GIF conversion as an
`OWNER ACTION` tooling step. Never fabricate a GIF or claim a capture that
wasn't recorded (rule 0 / evidence bar).

**AD-7 — Blog post is DRAFTED, titled after the REAL improvement, never
published by the model.** Before writing one number: reconstruct the actual
metric history from committed sources (`evals/reports/*.md`, `baseline.json`,
`WEEK2_*`/`WEEK3_RESULTS.md`, `git log`). Establish the true before/after. If
recall@5 didn't materially move (it didn't, per §1), the title is NOT "Recall@5
from X→Y" — it's the improvement that IS real and documented (the τ-tuning
must-abstain leak 25%→0% zero-hallucination story, and/or citation precision),
with recall@5 reported honestly as "stable at 0.863, and here's why that's the
right number, not a bigger one". Draft to `docs/BLOG_DRAFT.md` (or
`blog/`), including the `/evals` screenshot from Phase 3 and the demo frame from
Phase 5. **OWNER ACTION**, not the model's: publishing the post, making the repo
public, adding the CV link (spec §15 "repo public, post published, link on CV").
The model stops at a reviewable draft.

---

## 4. Phase plan (execute in order; every step has a verify line)

### Phase 0 — Orientation + the real-numbers baseline (no feature code)
1. Read spec §8, §10, §11, §15 + CLAUDE.md + this file. Read `evals/baseline.json`,
   skim `evals/reports/*.md`, read `app/evals/page.tsx` (the shell),
   `apps/api/app/routes/evals.py`, `apps/api/app/models.py` (Eval*Out),
   `core/groundcite/services/eval.py` (`list_runs`, `get_report` — do NOT touch),
   `ports/protocols.py` (the eval reads), `domain/results.py` (EvalRun/EvalResult).
2. Reconstruct the ACTUAL metric history from committed sources + `git log` +
   the 13 persisted runs. Write down the real before/after for each headline
   metric — this is the factual spine of both the README table (AD-6) and the
   blog (AD-7). No feature code yet.
   → **verify:** both dev servers up (`uvicorn` :8000, `npm run dev` :3000);
   `/healthz` 200; `/evals` shell renders; a one-paragraph "real numbers" note
   written from committed data, ready to feed Phases 5–6.

### Phase 1 — Backend read extension (AD-2; the only core/API work)
3. Repository read for eval-case metadata + `started_at`/`suite` on runs; add a
   `Case` domain type only if none exists. Extend the API run-detail response
   model to carry per-case case-metadata + metrics; compute per-run aggregates
   from persisted rows in the service/route. Unit tests with `FakeRepository`
   first (rule 3).
   → **verify:** ruff, ruff format, mypy --strict core (BOTH install states —
   hide/restore `openai`/`FlagEmbedding`/`rerankers` + `--no-incremental`, the
   proven ritual), import-linter 5/5, core pytest; api ruff + `mypy app tests` +
   pytest. Live-DB integration: `GET /eval/runs` → 13; a real run's detail
   carries `question` + `expected_clauses` per case; a `curl` transcript of one
   run detail pasted in the commit. ONE commit:
   `feat(core+api): eval-case reads for the /evals drill-down (Week 5 AD-2)`.

### Phase 2 — recharts dep + TS mirrors (AD-4)
4. Spec §11 table row (charting → Buy → recharts), pinned exact in
   `package.json`, `package-lock.json` re-committed — same commit as first use
   (rule 11). Update the TS response mirrors in `lib/api.ts`
   (`EvalRunOut`/`EvalResultOut`/`EvalRunDetailOut` gain the new fields) to match
   Phase 1's Python EXACTLY.
   → **verify:** `tsc --noEmit` clean (strict, grep the diff for `any`),
   `eslint .` clean, `next build` clean; `npm ls recharts` shows the pinned
   version. (This can fold into Phase 3's commit if the diff is small — one
   feature per commit, rule 7; a recharts-only commit with no consumer is fine
   too if it keeps the diff clean.)

### Phase 3 — the `/evals` page (the blog screenshot)
5. AD-1 + AD-3 + AD-4: runs table (suite, git_sha, date, τ/model from config,
   the three headline aggregates) → select a run → per-suite metric chart
   (honest grouped bars) + per-case drill-down (expected vs cited, hit/miss
   highlight, abstention correctness, latency, top_score). All server state via
   `useQuery` (rule 6). Mono on every clause id / score / sha (§2.2).
   → **verify:** BROWSER demo against the real API + the 13 real runs —
   screenshot the runs table, the chart, and an expanded per-case drill-down
   (both a grounded case and a must-abstain case). Zero console errors. Mono-font
   audit. Mobile viewport collapses cleanly. This screenshot is a blog asset —
   capture it well.

### Phase 4 — Abstention polish (AD-5)
6. Surface `AbstentionReason` in §2.2 tone; link closest-passage cards into the
   reader (reuse the Phase-8 deep-link); confirm first-class (amber, not error)
   framing. No threshold/prompt change (rule 4).
   → **verify:** BROWSER — a real grounded ask (unchanged) and a real abstention
   (DO-178C, free): reason shown, a closest-passage card click lands on the
   reader at that clause. Screenshot both. Zero console errors.

### Phase 5 — README benchmark table + demo capture (AD-6)
7. README §8 benchmark table from `baseline.json` + the committed first (τ=0.35)
   baseline for contrast; honest `negative`-suite footnote. Record the full §15
   loop + `/evals` via scratchpad Playwright `page.video()`; convert to GIF if
   tooling exists, else deliver webm + frames and flag conversion as OWNER
   ACTION.
   → **verify:** README table numbers match `baseline.json` exactly (diff them,
   don't eyeball); the capture file exists and was actually recorded (paste the
   path + duration); a key frame referenced in the commit.

### Phase 6 — Blog post draft (AD-7)
8. Draft `docs/BLOG_DRAFT.md` — the honest improvement narrative from Phase 0's
   verified numbers, the `/evals` + demo assets embedded, the bad first baseline
   committed in the story (spec §8). Title reflects the REAL delta, not a
   fabricated recall X→Y.
   → **verify:** every number in the draft traceable to a committed source
   (baseline.json / a report / a results doc); the draft explicitly labels what
   improved and what stayed stable-and-why. This is a `docs:` commit. **Do NOT
   publish. Do NOT make the repo public.**

### Phase 7 — Close-out
9. Full gates everywhere: core (ruff/format/mypy both states/import-linter/
   pytest), api (ruff/format/`mypy app tests`/pytest), web (tsc/lint/build).
   Push; CI green (3 jobs). Write `docs/WEEK5_RESULTS.md` (same honesty pattern
   as Week 3/4): what shipped, screenshots/transcripts, the AD-3 "no literal
   retrieved list" decision and any AD deviations, residuals. Add the spec §15
   scope-armor note to `docs/ROADMAP.md` (create it if absent) so post-Week-5
   ideas have a home that isn't code.
   → **verify:** CI green on the final sha; `WEEK5_RESULTS.md` committed;
   README quick-start still accurate. Then hand the OWNER the checklist: make
   repo public, publish blog, CV link.

---

## 5. Explicitly OUT of scope (do not touch)

- **Re-running any suite / any `eval run`** — the numbers are frozen at
  `19de5cd` (baseline.json). The page reads persisted data (rule 4, AD-1/AD-3).
- **The eval writer/scorer** (`services/eval.py` `run_full`/`run_retrieval`),
  chunking, retrieval, fusion, thresholds, prompts (rule 4 armor).
- **`evals/suites/*`** (rule 13) — read-only this week; not modified.
- **The literal retrieved top-k list on the drill-down** (AD-3) — needs an
  eval-writer change + a re-run; Week-6+ if ever.
- **Making the repo public, publishing the blog, the CV link** — OWNER ACTION.
- **The Week-4 residuals**, except the two that Phase 3/4 close naturally
  (closest-passage cards now link to the reader; the `/evals` page is the last
  page). The others (CitationOut lacks a doc id → multi-doc; abandoned-SSE
  thread leak; clause_path collation order; reader virtualization; CI can't run
  baseline eval) stay flagged, NOT fixed — spec §15 scope armor. If any feels
  urgent, it goes to `docs/ROADMAP.md`, not code.
- Judge/faithfulness metrics (still no second provider key; `faithfulness` stays
  null on the page — show it honestly as "not measured", don't hide the column).
- Auth, multi-tenancy, new corpora, Qdrant, MCP server (§16 extensions).

## 6. Environment facts (save yourself the rediscovery)

- Windows 11; PowerShell 5.1 primary (no `&&`); Git Bash preferred for
  long/detached runs. `docker exec groundcite-db psql -U groundcite -d
  groundcite` reads the eval data directly (user is `groundcite`, not
  `postgres`; DB on host port **5433**).
- Core venv `core\.venv\Scripts\python.exe`; api venv `apps\api\.venv\...`.
  Node v24.15.0, npm 11.12.1. Ports: web 3000, api 8000, Postgres 5433.
- 13 eval runs are already persisted (4 shas × 3 suites + 1 stray). `faithfulness`
  is null everywhere (no judge run). Only FULL runs are persisted.
- Real browser verification: scratchpad Playwright (chromium-cli unavailable
  here) — the Week-4 scripts under
  `…\scratchpad\playwright-check\` are the template; `page.video({dir})` records
  the demo. Not a project dependency.
- mypy CI-parity ritual for core changes: hide/restore
  `openai`/`FlagEmbedding`/`rerankers` site-packages + `--no-incremental`
  (copy Week 3/4's pattern, don't rediscover it).
- Groq free-tier quota still applies, but this week spends ZERO Groq tokens on
  evals (no re-runs) — only the handful of live `/ask` smokes for the abstention
  polish demo (~3K tokens each).

## 7. Evidence bar (how your work gets accepted)

Every commit that changes behavior carries, in its message: the commands run and
their real output — a `curl` transcript for the extended eval-detail route,
test-suite tails, and for the web phases real browser screenshots (the `/evals`
page and the abstention polish, captured against the 13 real runs and a live
ask). The Week-5 deliverable is a page that becomes a blog screenshot and a
benchmark table that must match `baseline.json` to the digit — a number that was
never actually measured, or a capture that was never actually recorded, does not
merge. When the data won't support the story you wanted (the recall@5 X→Y that
isn't there), the honest reframing IS the work (spec §8): the bad/flat number,
stated plainly with the reason, is more credible than a dressed-up one — and
that credibility is the entire point of shipping an eval harness in public.
