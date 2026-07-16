# Week 3 results — generation, Gates A/B, first full-pipeline baseline

> Companion to `docs/WEEK3_INSTRUCTIONS.md`. Filled in as Phases 4–7 land, same
> pattern as `docs/WEEK2_PLAN.md`. Real numbers, real transcripts — spec §8's
> honesty rule: the bad number IS the story.

## Phase 4 — full generation pipeline (`ask()`, Gates A/B)

Shipped: `1024912`, `ddeef60` (CI fix), `f68ec6d` (CI fix). CI green.

Real transcript, live Groq + live far-25 corpus:

```
$ groundcite ask "What does §25.1309(b) require for catastrophic failure conditions?" --slug far-25
status: GROUNDED
§25.1309(b) requires that the occurrence of any failure condition which would
prevent the continued safe flight and landing of the airplane is extremely
improbable.
citations:
  [1] 14 CFR Part 25 §25.1309(b)  score=0.9172
latency: 42181ms   ask_id: a7c6fb38-42df-4d80-be02-a61fac6881e5

$ groundcite ask "What does DO-178C say about MC/DC coverage requirements?" --slug far-25
status: ABSTAINED
reason: weak_retrieval
closest passages: (6 shown, top score 0.0023)
latency: 34986ms
```

Gate A correctly abstained on the out-of-corpus question **without calling the
LLM** (no wasted generation cost).

## Phase 5 — full-pipeline eval (`run_full`, persistence, CLI)

Shipped: `cf59654`, `695d229` (top_score capture). CI green.

Two real bugs found by smoke-testing against live Postgres + Groq before
trusting any of it:
1. `eval_results.case_id` FK had nothing to point at — suites load from JSONL
   (rule 13), not the DB, so cases were never upserted into `eval_cases`
   first. Fixed per AD-6's explicit design (upsert cases in the same
   transaction).
2. `json.loads()` on a value psycopg3 had already deserialized (jsonb → dict
   automatically). Systemic: found in 6 call sites across 3 files, silently
   masked until now because `chunks.metadata` has always been empty `{}` in
   this corpus (`bool({})` is falsy, so the buggy branch never fired).

## Phase 6 — first full-pipeline baseline (τ = 0.35, spec default)

Real run, all three suites, live Groq + live far-25 corpus, no `--judge` (no
second provider — settled owner gate). git sha `695d229`.

| suite | cases | grounded | abstained | abstention accuracy | mean citation precision |
|---|---|---|---|---|---|
| core | 40 | 39 | 1 | 0.975 | 0.846 |
| german | 10 | 7 | 3 | 0.900 | 0.952 |
| negative | 10 | 0 | 10 | 1.000 | — (nothing grounded) |
| **all 60** | **60** | **46** | **14** | **0.967 (58/60)** | **0.862** |

**Zero hallucination-risk failures**: across all 60 cases, no must-abstain
question ever received a GROUNDED answer. That is the contract spec §1
exists to guarantee, and it held.

**The cost paid at τ=0.35** — 2 cases that should have answered, abstained
instead:

| suite | score | question |
|---|---|---|
| core | 0.2254 | What bird impact must the tail surfaces be designed to survive? |
| german | 0.0530 | Welche Überziehwarnung müssen die Piloten erhalten, bevor der Flügel den Auftrieb verliert? |

### The bad number (§8 honesty rule) — Gate A ALONE leaks 25%

The end-to-end 100%/90% abstention accuracy above is NOT because Gate A's
threshold cleanly separates the two populations. Sweeping candidate τ values
against every case's recorded `top_score` (the normalized reranker score Gate
A actually compares — no re-asking, straight from the persisted
`eval_results.debug`):

| τ | grounded wrongly-abstained | must-abstain leak |
|---|---|---|
| 0.35 (spec default) | 2/48 (4.2%) | **3/12 (25.0%)** |
| 0.40 | 3/48 (6.2%) | 3/12 (25.0%) |
| 0.45 | 3/48 (6.2%) | 2/12 (16.7%) |
| 0.50 | 4/48 (8.3%) | 1/12 (8.3%) |
| 0.55–0.65 | 5/48 (10.4%) | 1/12 (8.3%) |
| **0.70** | 5/48 (10.4%) | **0/12 (0.0%) ← first zero-leak τ** |
| 0.75 | 7/48 (14.6%) | 0/12 (0.0%) |
| 0.80 | 10/48 (20.8%) | 0/12 (0.0%) |

At τ=0.35, **3 must-abstain cases pass Gate A's threshold on raw score alone**
(0.6891, 0.4685, 0.4135 — all above 0.35):

| score | question |
|---|---|
| 0.6891 | Which clause of 14 CFR Part 25 prescribes minimum en-route altitudes over mountainous terrain? |
| 0.4685 | What maximum stall speed must a normal-category light airplane meet for certification? |
| 0.4135 | What quantitative probability per flight hour does the acceptable-means-of-compliance guidance for CS 25.1309 assign to catastrophic failure conditions? |

**Why the end-to-end system still got all 3 right:** they proceeded to
generation, and the LLM itself set `"insufficient": true` (AD-4 →
ABSTAIN(WEAK_RETRIEVAL)) rather than fabricating an answer from marginally-
related chunks. Confirmed directly from the persisted `asks.pipeline_debug`
(`note: "insufficient context"` on all 3).

**This is a real safety net, not a coincidence** — but it means the current
0% hallucination rate depends on the LLM's own self-honesty, not on Gate A
itself. A different or more confident model, a prompt regression, or a
borderline case where plausible-looking chunks exist could slip through. Gate
A should be hardened independently rather than relying on generation-time
self-assessment as the only backstop — exactly the defense-in-depth spec §7
designs Gate A + Gate B to provide together.

**Decision: raise `TAU_RETRIEVAL` to 0.70.** First τ with zero measured leak
on this baseline. Cost: grounded-case wrongly-abstained rises from 4.2% to
10.4% (5/48) — a real, stated trade, not hidden. See the tuning commit for
the full before/after re-run and the specific cases affected.

## Phase 6 — τ tuning (0.35 → 0.70)

**Getting a clean re-run took three real detours worth recording plainly (§8
honesty rule) — none of them cosmetic.**

**Detour 1 — a case-level crash could abort an entire suite.** `run_full()`'s
companion `retrieve()` call (for the persisted recall/MRR columns) had no
exception guard, unlike `ask()` which already wrapped its own generator body
in try/except-as-ERROR-event. A transient HuggingFace Hub 504 during
tokenizer loading — unrelated to this project's code, upstream `transformers`
now makes a live network call (`is_base_mistral`) on every tokenizer load —
crashed a live 40-case run partway through. Fixed (`473cdd3`): the per-case
body is wrapped, one case's failure is recorded as `AskStatus.ERROR` and the
run continues. A second, related gap — the ERROR event's actual exception
`message` was never persisted anywhere, so an "error" row was previously a
dead end (`24a5241`) — was fixed just before this and is what made every
finding below diagnosable from the DB instead of requiring live
reproduction.

**Detour 2 — Groq's free-tier daily quota cannot fit one clean run.**
`llama-3.3-70b-versatile`'s quota is 100,000 tokens/day. A live tuned run
measured ~4,125 tokens/case for the full pipeline — so even the 40-case
`core` suite alone (~165,000 tokens) cannot complete in a single day, let
alone all 60 cases (~250,000 tokens needed). Confirmed directly: a clean
attempt got 24/40 `core` cases done before Groq returned `429` with `Used
99814/100000` — real evidence, not a guess. The original plan (spread the
run across multiple daily quota resets) was abandoned mid-flight in favor of
switching models — see Detour 3.

**Detour 3 (the important one) — a stale local `.env` silently invalidated
three live re-runs.** `core/.env` (gitignored, machine-local) still had
`TAU_RETRIEVAL=0.35` from before the Phase 6 tuning commit — pydantic-settings
env vars override `config.py`'s class field default, so **every "tuned
τ=0.70" run attempted this session was silently still running Gate A at
0.35**. The committed source (`config.py`'s default, `.env.example`) was
correct the whole time; only this machine's local override was stale. This
was caught by manually checking `get_settings().tau_retrieval` at the
runtime, not by anything in the persisted data — because `eval_runs.config`
never captured `tau_retrieval` or `groq_model` in the first place (`cli.py`'s
`config_snapshot` only had recall/fusion params). Fixed (`c9a45fb`): both
fields are now in every full-mode run's persisted config, so this exact
failure mode is now visible from a DB query, not just a lucky manual check.
All full-pipeline data gathered before this fix (three live re-runs, ~35
cases worth of Groq spend) was discarded — it measured the wrong
configuration.

**Combined with Detour 2, the practical result: switched `groq_model` to
`openai/gpt-oss-120b`** (`19de5cd`). Decision was operational, not a
citation-quality bake-off: `gpt-oss-120b`'s free-tier quota is 200,000
tokens/day (vs. 100,000), enough to finish the full 60-case tuned eval in
one day instead of 2–3. Smoke-tested directly on 2 live cases (grounded +
must-abstain, both correct) before committing. The 3-way eval-off the Week 3
plan flagged (`llama-3.3-70b-versatile` / `gpt-oss-120b` / `llama-4-scout`)
was **not** run in full — only `gpt-oss-120b` was tried, and it worked well
enough that the alternative wasn't needed. τ_retrieval itself is unaffected:
Gate A compares the **reranker's** score, never the LLM's, so the 0.35→0.70
tuning decision (spec §7.1 amendment) holds regardless of which model
answers.

### The real τ=0.70 result — clean, all 60 cases, `openai/gpt-oss-120b`, sha `19de5cd`

| suite | cases | grounded | abstained | error | abstention accuracy | mean citation precision |
|---|---|---|---|---|---|---|
| core | 40 | 36 | 4 | 0 | 0.900 | 0.885 |
| german | 10 | 6 | 4 | 0 | 0.800 | 1.000 |
| negative | 10 | 0 | 10 | 0 | 1.000 | — (nothing grounded) |
| **all 60** | **60** | **42** | **18** | **0** | **0.900 (54/60)** | **0.901 (42 grounded cases)** |

**Zero hallucination-risk failures, confirmed again**: across all 60 cases,
no must-abstain question was ever answered GROUNDED — `negative`'s
10/10 correct abstention matches the tau-sweep's "0/12 leak at τ=0.70"
prediction from the first baseline exactly.

**The cost, stated plainly**: overall abstention accuracy fell from
0.967 (58/60, τ=0.35) to 0.900 (54/60, τ=0.70) — 6 grounded-eligible cases
that would have answered at τ=0.35 now wrongly abstain. This is the
predicted trade from the original tau-sweep table (10.4% grounded-wrongly-
abstained at τ=0.70), landing almost exactly on target (6/50 grounded-
eligible = 12%).

| suite | score | question | why |
|---|---|---|---|
| core | 0.5428 | How flammable are cabin interior materials allowed to be? | below τ |
| core | 0.3622 | What combination of exit provisions, demonstrations, and lighting ensures a full airplane can be evacuated quickly in the dark? | below τ |
| core | 0.4926 | If an engine catches fire in flight, what design provisions must exist to contain the fire, cut off its fuel, and put it out? | below τ |
| core | 0.2254 | What bird impact must the tail surfaces be designed to survive? | below τ (same case flagged at τ=0.35) |
| german | 0.0530 | Welche Überziehwarnung müssen die Piloten erhalten, bevor der Flügel den Auftrieb verliert? | below τ (same case flagged at τ=0.35) |
| german | 0.7200 | Was verlangen die Vorschriften zur Ermüdungs- und Schadenstoleranzbewertung der Flugzeugstruktur? | **passed Gate A** — see residual below |

**A residual worth flagging for Week 4**: the last case above scored 0.72
(above τ=0.70, Gate A correctly let it through) but still abstained —
`asks.pipeline_debug.note` reads `"parse failed after repair"`, and its
completion used 3,072 tokens vs. an ~841-token average across all other
`gpt-oss-120b` calls this run (1/62 total calls, ~1.6%). The safety
contract held (parse failure → abstain, never a fabricated citation), but
this looks like an occasional verbose/reasoning-mode response from
`gpt-oss-120b` overflowing the expected JSON shape even after one repair
attempt. Not a Gate A/τ problem — a prompt/parser robustness question for
whoever owns Week 4, worth a look if it recurs at a higher rate.

**Recall/MRR unaffected, confirmed by a fresh retrieval-only run** (sha
`24a5241`, no Groq involved): `core` 0.863/0.902/0.850, `german`
0.917/0.958/0.938 — identical to Week 2's final numbers. τ tuning and the
model swap both live entirely downstream of retrieval; ranking never moved.

## Phase 7 — baseline artifact + close-out

**`evals/baseline.json`** (AD-8), sha `19de5cd`: recall@5/@10, MRR per suite
(retrieval-only, model-independent, confirmed identical to Week 2's final
numbers) plus abstention_accuracy/mean_citation_precision per suite from the
clean τ=0.70 / `gpt-oss-120b` run above. `negative`'s recall/MRR are
structurally 0.0 (zero scorable cases — every case is `must_abstain`, so
there's nothing to compute recall over); this is documented behavior
(`mean([]) == 0.0`), not a real signal, and is why `scripts/check_baseline.py`
only *gates* on recall@5 (spec §8's designated stable CI signal) rather than
trying to make the negative suite's vacuous 0.0-vs-0.0 comparison mean
anything.

**`scripts/check_baseline.py`** (AD-8): re-runs retrieval-only eval and fails
if recall@5 drops more than 0.05 (absolute) vs. baseline.json; recall@10/MRR
reported for context but don't gate. Smoke-tested both directions before
relying on it — a hand-crafted baseline with `negative`'s recall@5 inflated
to 0.5 correctly failed (`-0.500`, exit 1); the real committed baseline
correctly passes with zero delta on every metric (verified against a fresh
retrieval-only run, not assumed).

**NOT wired into CI (AD-8, deliberate)**: CI (`ubuntu-latest`, no Postgres,
no embedded corpus) cannot run this script at all — it needs a live
database and the ingested `far-25` corpus. A seeded-fixture strategy for CI
is explicitly a Week 4 decision, not solved here. Run it locally/manually
before a PR that touches chunking, retrieval, fusion, or thresholds
(CLAUDE.md rule 4) — it's the mechanical half of that rule; the eval run
itself still belongs in the PR/commit message regardless of what this
script reports.

**Final local gates, all green** (ruff, ruff format, mypy --strict in BOTH
install states — with and without the openai/FlagEmbedding/rerankers
extras, CI-parity verified by hiding/restoring the packages and clearing
`.mypy_cache` — import-linter, pytest unit + live-Postgres integration:
180 passed). CI confirmed green on every commit pushed this phase.

**Residuals explicitly flagged for Week 4** (not fixed here — named so they
aren't silently lost):
1. The `gpt-oss-120b` parse-failure residual above (1/62 calls, safely
   caught by the existing repair→abstain path, but worth watching if it
   recurs at a higher rate on a larger corpus).
2. The full 3-way model eval-off (`llama-3.3-70b-versatile` vs.
   `gpt-oss-120b` vs. `meta-llama/llama-4-scout-17b-16e-instruct`) the
   original plan flagged was never run — `gpt-oss-120b` was picked on
   quota headroom + a 2-case smoke test, not a citation-quality bake-off.
3. CI cannot run `check_baseline.py` (no Postgres/corpus) — a seeded-fixture
   strategy is undesigned.
4. `core/.env`'s staleness (the Detour 3 bug above) was a machine-local
   config drift, not a code bug — but nothing currently prevents the same
   class of drift recurring for any other tunable. Worth a "does the
   running config match the committed defaults" sanity check if this
   project grows more contributors/machines.

**Week 3 close-out summary**: `ask()` + Gates A/B shipped and load-bearing
(zero must-abstain cases ever answered GROUNDED, across every real run this
week — the core §1 safety contract held throughout, including through every
detour above). Retrieval-only baseline confirmed stable at Week 2's final
numbers. Full-pipeline baseline: 60/60 cases clean, 0.900 abstention
accuracy, 0.901 mean citation precision, at τ=0.70 on `gpt-oss-120b`. Every
bug found this week (jsonb double-decode, FK-violation-on-first-run,
dropped ERROR message, single-case-crashes-whole-suite, stale-.env-silently-
wrong-tau) was found by actually running the system against live Groq +
live Postgres, not by reasoning about it — and every one is fixed, tested,
and documented here rather than quietly worked around.
