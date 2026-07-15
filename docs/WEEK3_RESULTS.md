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

_(filled in after the tuned re-run)_

## Phase 7 — baseline artifact + close-out

_(filled in after Phase 7)_
