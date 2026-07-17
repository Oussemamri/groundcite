# Week 5 results — the `/evals` page, abstention polish, README + demo, blog draft

> Companion to `docs/WEEK5_INSTRUCTIONS.md`. Same pattern as
> `docs/WEEK3_RESULTS.md`/`docs/WEEK4_RESULTS.md`: real transcripts, real
> numbers, real screenshots — spec §8's honesty rule: the bad number IS the
> story. This is the last feature milestone (spec §15) — see
> `docs/ROADMAP.md` for scope armor going forward.

Every phase below shipped as its own commit, gates green locally before
every push, CI confirmed green on GitHub Actions after every push before
moving on. `evals/suites/*` (rule 13, human-owned) was never touched, and
no eval suite was re-run (rule 4 armor) — every number in this doc and in
the shipped UI comes from the 13 runs already persisted at the start of the
week (frozen at `evals/baseline.json`, sha `19de5cd`).

## Phase 1 — core+api eval-case reads (`86a45e6`, AD-2, the only backend work)

Repository read extension, port + `pg_repo` + `FakeRepository` in lockstep
(Week-4 AD-4 discipline): `EvalRun` domain gained `started_at` + `suite`
(suite derived by a correlated SQL subquery joining `eval_results` →
`eval_cases` — no schema change, since every case in one run shares a
suite); `Repository.get_eval_cases(case_ids)` added for the case-metadata
join the drill-down needs. Reused the existing `EvalCase` domain type
(spec §2.1 "Case") rather than inventing a new one — it already had exactly
the fields needed.

`apps/api`'s `EvalRunOut` gained `started_at`/`suite`; `EvalResultOut`
gained `question`/`expected_clauses`/`must_abstain`/`language` (joined from
`EvalCase`, `None` when a case id is unknown — never fabricated); a new
`EvalRunAggregatesOut` computes per-run headline metrics (mean
recall@5/@10/MRR, mean citation precision, abstention accuracy) from the
persisted per-case rows in the route — never by re-running.

Unit tests with `FakeRepository` first (rule 3): case join (incl. unknown
case id → dropped, not fabricated), `EvalService.get_cases` delegation, an
aggregates fixture hand-computed and checked. Then a live-DB check against
the real 13 runs: `GET /eval/runs` → 13, a real 40-case core run's detail
carries `question`/`expected_clauses` per case, aggregates computed live
(`mean_recall_at_5=0.8625`, close to but not identical to
`baseline.json`'s separately-recorded 0.863 — expected, not a bug: this
endpoint reads one run's own rows, `baseline.json` is a distinct committed
snapshot).

core: 199 passed (was 193 at Week 4 close, +6). api: 55 passed (was 50, +5)
+ 9/9 live-DB integration (1 new test). mypy --strict clean both install
states, import-linter 5/5.

## Phase 2+3 — recharts + the `/evals` page (`72fde31`, AD-1/AD-2/AD-3/AD-4)

`recharts` 3.9.2 pinned exact, spec §11 table row added same commit (rule
11, charting = Buy, owner-decided per AD-4). `lib/api.ts` TS mirrors
updated field-for-field to match Phase 1's Python.

The page: a runs table (suite/git_sha/date/τ/model + the three headline
aggregates, one row per persisted run, 13 real rows, per-row aggregate
fetch mirrors `/library`'s existing `DocumentRow` pattern) selects a run; a
per-suite grouped bar chart shows each suite's LATEST run's three headline
metrics — deliberately not a cross-config time series, since the four
tracked git_shas span τ=0.35→0.70 and a model swap, and a connecting line
would imply a false comparability; each bar's git_sha is named in the
tooltip. A per-case drill-down (`lib/clauseMatch.ts` ports
`core/services/metrics.py`'s exact sub-paragraph clause-matching rule,
presentational only, recomputes no stored metric) renders expected-vs-cited
clauses with a hit/miss highlight, the stored numbers, and abstention
correctness.

**Chart color, per the `dataviz` skill's procedure**: 3 chart-only series
colors, not the app's `grounded`/`abstained` status accents (which stay
reserved for ask-outcome status elsewhere) — validated CVD-safe against the
app's real dark surface (`#131822`) via the skill's validator script before
use: all 3 checks pass.

**Two real bugs found live, neither caught by `tsc`/`eslint`** (browser-
verified via scratchpad Playwright against the real API + all 13 persisted
runs, zero console errors throughout):
1. Recharts' default bar-growth animation raced Chromium's `fullPage`
   screenshot resize — the SVG had fully correct, non-empty bar geometry
   (confirmed via computed styles + bounding boxes: real `fill`, real
   `height`, real screen coordinates) but rendered as empty bars in a
   full-page capture taken after the animation should have finished. Same
   class of paint-timing artifact as Week 4's SPA-navigation finding.
   Fixed: `isAnimationActive={false}` on every `<Bar>` — also the better
   call for a static analytics page, not just a test workaround.
2. The runs-table Model column showed "retrieval-only" for any run missing
   `groq_model` in its config snapshot. But AD-1 guarantees ONLY
   full-pipeline runs are ever persisted — this was mislabeling real full
   runs. The 3 older git_shas' config snapshots predate the `groq_model`
   key (confirmed via a live query: `llm_provider="groq"` and `judge=false`
   both present on every one of them). Fixed to fall back to
   `llm_provider` instead of fabricating a claim the data doesn't support.

A third finding, not a bug: Chromium's `fullPage` screenshot duplicates the
sticky nav header mid-page when captured after a click changes page height
(confirmed only one `<header>` exists in the DOM) — a capture artifact real
users never see; worked around with viewport screenshots after
`scrollIntoView` instead.

Gates: `tsc --noEmit` clean (strict, `any` grep on the whole week's diff:
zero hits), `eslint .` clean, `next build` clean.

## Phase 4 — abstention polish (`b9dcf2d`, AD-5)

Surgical, not a rebuild — `/ask` abstention already worked end-to-end from
Week 4. `AbstentionCard` gained an optional `reason` prop rendering one
calm §2.2-toned line naming the gate that fired (`weak_retrieval` → Gate A,
`uncited` → Gate B), additive under the spec-locked title/subtitle (both
verbatim, unchanged). `/ask` passes `stream.final.abstention.reason`
through.

The other two AD-5 items were already true from Week 4, re-verified live
here rather than rebuilt: closest-passage cards already link into the
reader (`CitationCard` used uniformly for citations and `top_passages`,
both carrying `documentSlug`); abstention already reads amber
(`#F5A623`), never red.

Live verification, zero console errors throughout: a real grounded ask
(§25.1309(b), confidence 0.9172, 3 citations) → clicked the first citation
→ landed on the reader with §25.1309(b) highlighted and its tree ancestors
expanded. A real abstained ask (DO-178C MC/DC, zero Groq tokens — Gate A
blocks pre-LLM, top score 0.0023) → "No grounded answer" / the spec
subtitle / the new "Gate A: no clause in the corpus scored above the
retrieval confidence threshold…" line / amber framing / 6 closest-passage
cards → clicked the first → landed on the reader with §25.858(d)
highlighted, confirming the closest-passage deep-link works identically to
a citation's, live, not just in code.

**Two testing-methodology findings, not app bugs**: (1) a screenshot taken
immediately after this SPA navigation onto the very tall, unvirtualized
reader page painted solid black — the exact compositor-flush artifact
`WEEK4_RESULTS.md` already documented for this page; a longer wait + a 1px
scroll nudge resolved it. (2) a `fullPage: true` screenshot on that page
hit a real Chromium screenshot-buffer limit (~700,000px tall) — switched to
viewport-only captures for reader screens.

## Phase 5 — README benchmark table + demo capture (`c611548`, AD-6)

README's new "Benchmarks" section: every number diffed programmatically
against its committed source before writing it down, not eyeballed —
retrieval numbers from `evals/baseline.json`, the first (τ=0.35) baseline
from `docs/WEEK3_RESULTS.md` Phase 6, the τ-sweep leak table from the same
doc. `negative`'s structural 0.0 recall is footnoted, not hidden;
`faithfulness` stated as genuinely unmeasured.

Demo capture: the full spec §15 loop recorded live (API :8000 DB-backed,
web :3000, real far-25 corpus) via scratchpad Playwright's `page.video()` —
`docs/demo/demo.webm`, 2.88 MB, **1m23s** (verified via Windows Shell file
properties, not guessed), zero console errors. 6 key frames + the Phase-3
`/evals` screenshot alongside it.

**GIF conversion flagged as OWNER ACTION** (`docs/demo/README.md`): neither
`ffmpeg` nor `gifski` is installed in this environment (`which ffmpeg` /
`which gifski` both checked and empty before claiming this) — delivered the
webm + frames per AD-6's explicit fallback rather than fabricating or
skipping the asset.

**Two real environmental incidents during this phase, unrelated to app
code, recorded because they cost real time and would trip up a re-run**:
1. Docker Desktop's engine crashed mid-session (`docker ps` / `docker info`
   failed with a named-pipe connection error) while the API server was
   still up but every DB-touching route — including `/healthz` — hung
   indefinitely waiting on a dead connection. Restarted Docker Desktop,
   waited for the `groundcite-db` container to report `healthy` again,
   confirmed `/healthz` recovered before continuing. Nothing in the
   application code was at fault or was changed for this.
2. Next.js 15's dev server hit a genuine React Server Components bundler
   bug twice after heavy client-side navigation during verification runs
   (`Could not find the module ".../segment-explorer-node.js#SegmentViewNode"
   in the React Client Manifest` / `__webpack_modules__[moduleId] is not a
   function`), which cascaded into a broken client bundle where form inputs
   stopped updating React state entirely. `next build` stayed green
   throughout (confirmed repeatedly) — this is a dev-mode-only HMR
   corruption, not a production/build issue. Fixed each time by killing the
   dev server, clearing `.next`, and restarting clean.

## Phase 6 — blog post draft (`2c77dd1`, AD-7)

`docs/BLOG_DRAFT.md`, **NOT PUBLISHED** (owner action). Reconstructed the
actual metric history from committed sources before writing one number, per
AD-7: `docs/WEEK2_PLAN.md` §3b's pre-persistence retrieval-tuning arc (core
recall@5 0.769 → 0.856 with the reranker → 0.863 with the de-hyphenation
fix — real movement, but it happened in Week 2 and has been flat across
every git_sha tracked since); `docs/WEEK3_RESULTS.md` Phase 6's Gate A
τ-sweep (25.0% must-abstain leak at τ=0.35 → 0.0% at τ=0.70, first
zero-leak τ) and its real stated cost (abstention accuracy on answerable
questions 0.967 → 0.900).

Per AD-7's explicit instruction — recall@5 didn't materially move across
the tracked history, so the title is not "Recall@5 from X→Y" — titled
around the real, documented improvement: **"How I Cut a Hallucination Leak
From 25% to 0% — and Why Recall@5 Didn't Move."** Embeds the Phase-3
`/evals` screenshot and links the Phase-5 demo capture. No new numbers
introduced beyond what Phases 0–5 already verified against committed
sources.

## Phase 7 — close-out

**Full local gates, all green, everywhere, re-verified from a clean state**
(not assumed carried over from earlier phases):

- **core**: `ruff check` / `ruff format --check` clean, `mypy --strict`
  clean in **both** install states (hid/restored the
  `openai`/`FlagEmbedding`/`rerankers` site-packages dirs + cleared
  `.mypy_cache`, the proven CI-parity ritual), `lint-imports` 5/5 contracts
  kept, `pytest` — **199 passed**.
- **api**: `ruff check` / `ruff format --check` clean, `mypy app tests`
  clean, `pytest` — **55 passed** (unit) + **9 passed** (live-DB
  integration, including the new Phase-1 case-metadata check).
- **web**: `tsc --noEmit` clean (strict, zero `any` across the whole week's
  diff — grepped, not assumed), `eslint .` clean, `next build` clean.

CI confirmed green on every commit pushed this week (5 pushes, 3 jobs each
— core+db, api, web — all green): `86a45e6`, `72fde31`, `b9dcf2d`,
`c611548`, `2c77dd1`.

`docs/ROADMAP.md` created (spec §15 scope armor: bugfixes only from here;
named residuals below have a home that isn't code). README's Status and
Roadmap sections updated to reflect Weeks 0–5 complete instead of
describing Week 5 as "planned, not yet executed."

### AD deviations from the instructions doc (stated, not silently forced)

None of the DECIDED architecture calls (recharts, AD-1 through AD-7) needed
to change to fit reality — every fact this file's Phase 0 orientation
turned up (13 persisted runs, the case-metadata gap, the missing
`groq_model` key on 3 older runs, recall@5's flatness) matched what
`WEEK5_INSTRUCTIONS.md` had already verified, or was a narrower live-browser
finding (the two real bugs in Phase 2+3, the two environmental incidents in
Phase 5) that got fixed within the existing plan rather than requiring a
plan change.

### Residuals explicitly flagged (not fixed here — named in `docs/ROADMAP.md` so they aren't silently lost)

1. **The literal retrieved top-k clause list is not on the drill-down**
   (AD-3, by design) — FULL runs persist recall@k numbers and cited
   clauses, not the ranked retrieved list itself. Needs an eval-writer
   change (`retrieved_clauses` in per-case `debug`) + a re-run; explicitly
   out of scope this week (rule 4) and not built speculatively.
2. **Mobile chart label crowding**: on a 375px viewport, two adjacent
   bars both at 100% have their direct-value labels overlap slightly.
   Cosmetic; the desktop capture is the primary blog/README asset and reads
   cleanly. Not fixed — noted so it isn't mistaken for an unnoticed bug.
3. **GIF conversion of the demo capture** — owner action, tooling not
   available in this environment (see Phase 5 above and
   `docs/demo/README.md`).
4. Every Week-4 residual not closed naturally by this week's phases stays
   flagged and unfixed, per spec §15 scope armor: `CitationOut` lacks a
   document identifier (still fine — one document in the library),
   abandoned-SSE thread leak on client disconnect, `list_chunks`'s
   collation-order clause_path, reader virtualization, CI's inability to
   run `check_baseline.py`. None revisited this week; all now live in
   `docs/ROADMAP.md` instead of only in an old results doc.

**Week 5 close-out summary**: the `/evals` page reads all 13 persisted eval
runs live and renders an honest chart and per-case drill-down over them;
abstention now explains itself; the README states the project's real
benchmark numbers including the embarrassing first baseline; a demo was
captured against the real running system, not staged; and a blog draft
exists that reports the metric that actually moved (a 25%→0% hallucination
leak) instead of manufacturing a bigger recall@5 number that isn't in the
data. Every bug found this week (a chart animation racing a screenshot, a
mislabeled retrieval-only column, two environmental infrastructure
incidents) was found by actually running the system — not by reasoning
about it — and every one is fixed or clearly flagged here, not quietly
worked around.

## Owner action checklist (spec §15 — outward-facing, hard to reverse, explicitly not the model's to do)

- [ ] **Make the repo public** on GitHub.
- [ ] **Publish the blog post** — review/edit `docs/BLOG_DRAFT.md`, then
      publish it wherever the owner publishes (own blog, dev.to, etc.).
- [ ] **Add the link to a CV** once the above two are live.
- [ ] *(Optional, flagged in `docs/demo/README.md`)* convert
      `docs/demo/demo.webm` to a GIF with `ffmpeg`/`gifski` if embedding a
      GIF in the published post is preferred over the webm.
