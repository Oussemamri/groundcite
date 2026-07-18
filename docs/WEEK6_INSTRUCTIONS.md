# Week 6 — `/ask` → multi-turn chat redesign: execution instructions

> Named "Week 6" for documentation continuity with Weeks 0–5, though it isn't
> a calendar week. This is a deliberate, owner-authorized reopening of spec
> §15's "bugfixes only" scope armor for one feature — stated plainly, not a
> silent scope violation. Captures the plan approved in a plan-mode session
> so the decision trail is durable, not just in that session's transcript.

## 0. Non-negotiable rules (unchanged from every prior week)

- CLAUDE.md rules 1–14 all still apply. In particular: rule 4 (any change to
  chunking/retrieval/fusion/thresholds/prompts needs an eval run) does
  **not** trigger this week — nothing in `AskService`'s pipeline logic,
  Gates A/B, retrieval, or prompts changes. Stated explicitly so it's clear
  this was checked, not overlooked.
- `evals/suites/*` stays untouched (rule 13, human-owned).
- Full local gates green before every commit, CI confirmed green after every
  push before starting the next phase — same discipline as Weeks 1–5.
- Live browser verification for every web change, real API + real far-25
  corpus, zero console errors, screenshots — `tsc`/`eslint`/`next build`
  passing is necessary, never sufficient.

## 1. The origin

Owner supplied a high-fidelity design handoff
(`design_handoff_chat_redesign/`, from `Professional AI chat web design.zip`)
redesigning `/ask` into a multi-turn chat experience: warm light "paper"
theme, collapsible sidebar with conversation history, 3-column shell.
Confirmed with the owner before planning:
- Full redesign including multi-turn chat (not visual-only).
- Light warm theme (`GroundCite Chat.dc.html`), add the new fonts (Source
  Serif 4 + JetBrains Mono) — reads as more professional.
- Spec updated as a deliberate pivot (this doc + `GROUNDCITE_PROJECT_SPEC.md`
  §2.2/§5/§9/§10, same commit).

## 2. The one architecture call that shapes everything else

**Conversations are a persistence/UI grouping, not conversational memory.**
Each turn still runs through `AskService.ask()` exactly as today — full
independent retrieval, Gate A, generation, Gate B — with **no prior-turn
context passed to the LLM**. Required by spec §3.2's unchanged non-goal ("No
agentic multi-step tool use. One ask = one pipeline run"). Confirmed against
the design mockup's own JS (`support.js`): its simulated `ask()` never sends
prior turns anywhere either. A conversation is a titled container over
already-independent `Ask` rows.

Practical effect: `core/groundcite/services/ask.py`'s pipeline logic,
prompts, gates, and retrieval are untouched. The only core change is a
`conversation_id` tag threaded through persistence.

## 3. Architecture decisions (DECIDED — implement, don't re-litigate)

**AD-1 (backend, core):** New `Conversation` domain type (id, title,
created_at, optional `turn_count`/`latest_status` populated only by
`list_conversations()` — same read-only-derived-field pattern as Week 5
AD-2's `EvalRun.suite`). `Ask.conversation_id: UUID | None`. Repository port
gains `create_conversation`, `get_conversation`, `list_conversations`,
`list_conversation_asks` — port → `pg_repo` → `FakeRepository` → unit tests →
live-DB integration, one commit, same lockstep discipline as every prior
Repository extension. New migration (not a rewrite of `0001`): `conversations`
table + `asks.conversation_id` nullable FK + index. `AskService` gains
`conversation_id` param threaded into `Ask` construction + the `FINAL`/`ERROR`
event payloads, plus thin repository-delegate methods (same file, mirrors
the existing `get_ask`/`get_ask_citations` pattern — no new service class).

**AD-2 (backend, api):** `ConversationOut`/`ConversationDetailOut` response
models. `GET /conversations`, `GET /conversations/{id}` (no `POST` — a
conversation only exists via a first ask). `AskIn.conversation_id: str |
None`; `asks_stream.py`'s route auto-creates a conversation (title = first
~80 chars of the question) when absent, else passes the given id through
unvalidated (an unknown id surfaces as a FK violation — acceptable, the web
client only ever sends ids it fetched from `GET /conversations`).

**AD-3 (title generation):** Literal first-question text, truncated to ~80
chars + ellipsis. No LLM summarization call — a real, separate scope item,
not built here (flagged in the results doc / ROADMAP.md).

**AD-4 (frontend, theme):** A second, distinctly-prefixed `chat-*` Tailwind
color token set (additive — zero risk to the existing dark tokens
`/library`/`/evals`/`/documents/[slug]` use). `Source_Serif_4` added via
`next/font/google`, identical pattern to the existing `Inter`/
`JetBrains_Mono` calls (self-hosted at build time).

**AD-5 (frontend, routing):** Next.js route groups — `app/(main)/layout.tsx`
(new) renders `<Nav />` for `/`, `/library`, `/evals`, `/documents/[slug]`
(moved into `(main)`, URLs unchanged); `app/ask/` stays outside `(main)`,
gets its own full-viewport chat shell with no `<Nav />`. `/ask` (fresh) +
`/ask/[conversationId]` (load a past one), mirroring the `/documents/[slug]`
precedent. A small "Library" / "Evals" text-link pair goes in the sidebar
near the corpus footer — the mockup has no way back to the rest of the app
at all, a real usability gap beyond the mockup's stated scope, not an open
design question.

**AD-6 (frontend, state):** Does **not** rewrite `useAskStream`
(`lib/sse.ts`) — that hook stays single-exchange; the chat page holds
`completedExchanges[]` locally, archiving the previous `useAskStream`
terminal state before calling `start()` again for a new turn. Loading
`/ask/[id]` seeds `completedExchanges` from `GET /conversations/{id}`.

**AD-7 (frontend, components):** `PipelineStatus`, `StatusChip`,
`CitationCard`, `AbstentionCard` are restyled **in place** (confirmed via
grep: all four are exclusively imported by `/ask`, zero other pages) — new
`chat-*` classes, same logic. New chat-only components live in
`app/components/chat/`.

**AD-8 (deliberately not built):** (1) inline clickable `[n]` citation
markers in the answer prose — the generator's `answer_md` contract has never
emitted inline markers (confirmed in `prompts/answerer.py`); building this
needs a prompt change, out of scope for a redesign, its own rule-4-gated
change. (2) mobile (<1360px) citation sheet/popover — the design's own
README says this was "not built in the mock" either. (3) conversation
rename/delete — not in the mockup's interaction list.

## 4. Phase plan (execute in order)

### Phase 1 — Spec pivot + this doc
`GROUNDCITE_PROJECT_SPEC.md` §2.2 (new §2.2.1 subsection), §5 (schema), §9
(API surface), §10 (`/ask` bullet rewrite). This file. No code yet.

### Phase 2 — `core`: conversation persistence (AD-1)
Domain type, port + `pg_repo` + `FakeRepository`, migration, `AskService`
methods. Unit tests with fakes (rule 3). Live-DB check against the real
compose Postgres. Full core gates (ruff, format, mypy --strict both install
states, import-linter, pytest).

### Phase 3 — `apps/api`: conversation routes (AD-2, AD-3)
Models, routes, `AskIn.conversation_id`, `asks_stream.py` wiring. Unit tests
via `dependency_overrides`; one live-DB integration test. Full api gates.

### Phase 4 — `apps/web`: theme + routing scaffold (AD-4, AD-5)
Tailwind `chat-*` tokens, `Source_Serif_4` font, route-group restructuring.
**Regression-check `/`, `/library`, `/evals`, `/documents/[slug]` render and
behave identically to before** — the move touches file locations, not logic,
but this gets verified live, not assumed. Full web gates.

### Phase 5 — `apps/web`: the chat page itself (AD-6, AD-7, AD-8)
Sidebar, header, thread, composer, citations panel; restyled shared
components; `/ask` + `/ask/[id]` routes; `lib/api.ts`/`lib/sse.ts` mirrors.
Full web gates.

### Phase 6 — Live verification
Scratchpad Playwright + a real multi-turn Groq smoke (2–3 real messages in
one conversation, ~3–6K tokens — same budget class as Week 5's abstention
verification): multi-turn thread rendering, an abstained turn mid-conversation,
sidebar switching, "+ New ask", citation→reader deep-link, mobile viewport
breakpoints (sidebar closed <1100px, citations hidden <1360px), reduced
motion, keyboard focus. Zero console errors throughout.

### Phase 7 — Close-out
`docs/WEEK6_RESULTS.md` (same honesty pattern as every prior results doc).
`docs/ROADMAP.md` gets AD-8's three deferred items as named residuals.
GitHub issue #13 closed with a link to the results doc.

## 5. Explicitly OUT of scope (do not touch)

- `core/groundcite/services/ask.py`'s retrieval/generation/gate logic,
  prompts, thresholds — AD architecture call above is binding.
- Any eval suite re-run (nothing gates on it this week).
- `/library`, `/evals`, `/documents/[slug]`'s visual theme — dark
  "mission control" stays exactly as-is.
- Conversation title LLM-summarization, rename/delete, inline citation
  markers, mobile citation sheet — all named in AD-3/AD-8 as deferred.
