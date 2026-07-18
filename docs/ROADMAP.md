# Roadmap

## Scope armor (spec §15, binding after Week 5 — Week 6 was a named, owner-authorized exception)

Weeks 0–5 shipped the full milestone list in `GROUNDCITE_PROJECT_SPEC.md`
§15: prep, ingestion, hybrid retrieval + the retrieval-only eval half,
generation + Gates A/B + the first full-pipeline baseline, the FastAPI + SSE
API and the `/ask`/`/library`/`/documents/[slug]` web app, and the `/evals`
page, abstention polish, an honest README benchmark table, a demo capture,
and a blog draft. That was the last SPEC-defined feature milestone.

**Week 6** (`docs/WEEK6_INSTRUCTIONS.md`/`docs/WEEK6_RESULTS.md`) reopened
this deliberately: the owner supplied a high-fidelity design handoff
redesigning `/ask` into a multi-turn chat experience, confirmed explicitly
before any code was written (full redesign incl. conversation persistence,
not a visual-only restyle) rather than silently expanding scope. It shipped
without touching `core/groundcite/services/ask.py`'s retrieval, generation,
gates, or prompts — spec §3.2's "one ask = one pipeline run" non-goal held
throughout; conversations only group already-independent Asks.

**From here forward (again): bugfixes only, unless another owner-supplied
design/feature request explicitly reopens scope the way Week 6 did.** New
ideas go here, not into code. This file is where they land instead — read
it before proposing a new feature branch. Landing a new idea in code
without it passing through here first (or an explicit owner go-ahead like
Week 6's) is itself a rule-7/rule-0 violation (scope creep), not just a
process nitpick.

## Ideas parked here (not started, not scheduled)

Carried over from residuals flagged in `docs/WEEK4_RESULTS.md`,
`docs/WEEK5_RESULTS.md`, and `docs/WEEK6_RESULTS.md` — real, named,
deliberately not built speculatively:

- **Inline `[n]` citation markers in the /ask answer prose** (Week 6 AD-8)
  — the generator's `answer_md` contract has never asked the LLM for inline
  markers (confirmed in `core/groundcite/services/prompts/answerer.py`);
  citations are a separate structured list. Building this needs a prompt
  change — its own rule-4-gated, eval-verified effort, not bundled into a
  redesign. (Also a pre-existing gap vs. spec §3.1 goal 3's literal
  wording, "inline citations `[...]`" — not newly introduced this week.)
- **A mobile (<1360px) citation sheet/popover for `/ask`** (Week 6 AD-8) —
  the design handoff's own README says this wasn't built in the mock
  either; the citations panel just hides below that width today.
- **Conversation rename/delete** (Week 6) — not in the design handoff's
  interaction list.
- **LLM-summarized conversation titles** (Week 6 AD-3) — titles are
  currently the literal opening question, truncated to ~80 chars. A real
  separate feature (a second LLM call, cost, a prompt to design and
  verify), not built speculatively.
- **A replayed abstained turn's closest passages are unrecoverable**
  (Week 6) — `Abstention.top_passages` is an SSE-only payload, never
  persisted to the `asks` table, so `/ask/[conversationId]` genuinely
  cannot show them for a reloaded past turn (confidence/threshold/latency
  still populate correctly, since those fields ARE persisted). Would need
  a real schema change (persist `top_passages` alongside `pipeline_debug`
  or in a new column) to close.

- **`Citation.document_slug`** — a real cross-layer field (core domain → API
  model → TS type) so citation→reader links stay correct once the library
  holds more than one document. Today's single-document library makes this
  invisible; it will break silently the moment a second document is
  ingested.
- **Cancellation-aware reranker calls** — an abandoned SSE connection
  currently leaves the CPU-bound rerank step running to completion
  server-side with nobody listening (Week 4 Phase 3). Needs a
  cancellation-aware call or a watchdog under real concurrent load.
- **`list_chunks`'s clause_path ordering** — currently DB collation order,
  not numeric clause order (Week 4 Phase 1). Cosmetic today because the
  reader renders from `get_section_tree` instead, which *is* correctly
  ordered; would matter if something ever renders chunks directly from
  `list_chunks`'s own order.
- **Reader virtualization** — the `/documents/[slug]` reader is fully
  unvirtualized (1,573 DOM chunk cards on far-25, ~700,000px tall). Accepted
  for v1; revisit if the corpus grows enough that it feels slow in real use
  (it hasn't, so far).
- **CI cannot run `scripts/check_baseline.py` or any real-embedding eval**
  (no Postgres corpus in CI, multi-GB models, wrong cost/flake budget for
  per-commit CI). A seeded-fixture strategy is undesigned. Stays a manual
  gate (CLAUDE.md rule 4) until someone designs one.
- **The literal retrieved top-k clause list on the `/evals` drill-down**
  (Week 5 AD-3) — not persisted for FULL-pipeline runs today (only the
  recall@k numbers and what got cited are). Needs an eval-writer change
  (store `retrieved_clauses` in per-case `debug`) + a re-run to populate
  historically. Explicitly deferred rather than faked.
- **`faithfulness` (Ragas judge metric)** — still null on every persisted
  run; needs a second LLM provider distinct from the answering model
  (judge ≠ answerer), not yet configured.
- **The 3-way generation-model eval-off** (`llama-3.3-70b-versatile` /
  `gpt-oss-120b` / `llama-4-scout`) the original Week 3 plan flagged —
  never run; `gpt-oss-120b` was picked on Groq quota headroom + a 2-case
  smoke test, not a citation-quality bake-off.
- **GIF conversion of the Week 5 demo capture** — `ffmpeg`/`gifski` not
  installed in the dev environment this was built in; `docs/demo/demo.webm`
  + key frames are the delivered asset. A one-command conversion once
  either tool is available (see `docs/demo/README.md`).

None of the above blocks anything currently shipped. They're named here so
they aren't silently lost, not because any of them is urgent.
