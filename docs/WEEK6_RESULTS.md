# Week 6 results — the `/ask` multi-turn chat redesign

> Companion to `docs/WEEK6_INSTRUCTIONS.md`. Same pattern as every prior
> week's results doc: real transcripts, real numbers, real screenshots —
> spec §8's honesty rule extends to UI work too: what's built pixel-faithful
> vs. deliberately deferred is stated plainly, not blurred.
>
> This week is a deliberate, owner-authorized reopening of spec §15's
> "bugfixes only" scope armor for one feature (an owner-supplied design
> handoff), not a silent scope violation — stated explicitly here as it was
> in `docs/WEEK6_INSTRUCTIONS.md` before any code was written.

Every phase below shipped as its own commit, gates green locally before
every push, CI confirmed green on GitHub Actions after every push before
moving on. `evals/suites/*` (rule 13, human-owned) was never touched. No
eval suite was re-run — nothing in `core/groundcite/services/ask.py`'s
retrieval, generation, gates, or prompts changed this week; conversations
are a persistence/UI grouping over already-independent Asks, never a new
generation capability (spec §3.2 "one ask = one pipeline run" is unchanged
and was the single architecture call every other decision this week hung
off of).

## Phase 1 — spec pivot + instructions doc (`8eae6e7`)

`GROUNDCITE_PROJECT_SPEC.md` updated in the same commit as the plan, per
the migration file's own rule (code and spec must not silently diverge):
new §2.2.1 (the `/ask` chat theme, explicitly scoped to that one page —
`/library`/`/evals`/`/documents/[slug]` keep §2.2's dark theme verbatim,
unchanged), §5 (the `conversations` table + `asks.conversation_id`,
verbatim), §9 (the two new routes), §10 (the `/ask` bullet rewritten).
`docs/WEEK6_INSTRUCTIONS.md` captures the architecture decisions (AD-1
through AD-8) approved in the plan-mode session that preceded this week, so
the decision trail is durable in the repo, not just in that session's
transcript.

## Phase 2 — core: conversation persistence (`49d26e9`, AD-1)

New `Conversation` domain type + `Ask.conversation_id` (nullable). Repository
port gains `create_conversation`/`get_conversation`/`list_conversations`/
`list_conversation_asks` — port → `pg_repo` → `FakeRepository`, same
lockstep discipline as every prior extension. `list_conversations` derives
`turn_count`/`latest_status` via a correlated subquery joining `asks` (same
technique as Week 5 AD-2's `EvalRun.suite`, no new aggregate table).
Migration `0002` (not a rewrite of `0001`): the table + nullable FK + index.
`AskService.ask()` gains an optional `conversation_id` param that ONLY tags
the persisted row and the terminal event's data — confirmed by grep that
every existing caller (CLI, `EvalService.run_full`) passes none and is
unaffected.

11 new unit tests with fakes (conversation_id tags the grounded/abstained/
ERROR paths; `FakeRepository`'s own create/get/list/list_conversation_asks
directly). One live-DB integration test appended to `test_pg_reads.py`,
verified against the real compose Postgres after applying migration `0002`.

Gates: core pytest **211 passed** (was 199 at Week 5 close), mypy --strict
clean both install states, import-linter 5/5.

## Phase 3 — api: conversation routes (`8c70aee`, AD-2/AD-3)

`GET /conversations`, `GET /conversations/{id}`. `POST /asks`'s `AskIn`
gains optional `conversation_id`; absent → the route auto-creates one
(title = first ~80 chars of the question, AD-3 — no LLM summarization call,
a real separate scope item, not built here).

**A real bug found live, not by reasoning about it**: `GET
/conversations/{id}` initially returned `turn_count`/`latest_status` as
`null` even for a conversation with a real persisted turn. Root cause:
`get_conversation()` (the single-row read) was never meant to populate
those fields — only `list_conversations()`'s correlated-subquery SQL does,
by design — but the detail ROUTE already has the full turn list in hand via
`list_conversation_asks()` and should derive them from *that* instead of
leaving them null. Fixed in the route layer (the same "compute in the route
from already-fetched data" pattern as Week 5's `EvalRunAggregatesOut`), not
by making `get_conversation()` do a second, redundant DB read. Caught by a
live-DB integration test written specifically to catch it — a real ask with
no `conversation_id`, fetched back via a real `GET /conversations/{id}`,
asserting `turn_count == 1` against the real Postgres row.

Gates: api pytest **66 passed** (unit) + **11 passed** (live-DB
integration, real Groq-free must-abstain asks, same zero-token pattern as
Week 5), mypy clean, ruff clean.

## Phase 4 — theme tokens, fonts, route-group scaffold (`7e2b66f`, AD-4/AD-5)

Additive `chat-*` Tailwind color set, zero risk to the dark tokens
`/library`/`/evals`/`/documents/[slug]` use. `Source_Serif_4` via
`next/font/google`, identical pattern to the existing `Inter`/
`JetBrains_Mono` calls (self-hosted at build time). `app/(main)/layout.tsx`
(new) renders `<Nav />` for every page except `/ask` (moved via `git mv`,
mechanical, URLs unchanged).

Live regression check (scratchpad Playwright, zero console errors):
`/library`, `/evals`, and a document-reader deep-link screenshot
pixel-identical to before the move; Nav still highlights the active route
correctly.

## Phase 5 — the chat page itself (`00a4971`, AD-6/AD-7/AD-8)

Built to the design handoff pixel-for-pixel where the backend contract
supports it. `lib/chatExchange.ts` normalizes two different wire shapes — a
live `useAskStream()` state and a replayed `AskOut` — into one `Exchange`
type `ExchangeCard` renders identically either way. Did **not** rewrite
`useAskStream` (stays single-exchange, well-tested); `ChatShell` archives
the previous live exchange into `completedExchanges` on each new submit,
and seeds it from history on `/ask/[conversationId]` load. A fresh
session's first message syncs the URL via the raw History API
(`window.history.replaceState`), not `next/navigation`'s router — a real
App Router navigation between `/ask` and `/ask/[id]` unmounts and remounts
the page, which would lose the in-progress thread exactly when it matters.

Restyled in place (confirmed via grep: exclusively used by `/ask`):
`PipelineStatus`, `StatusChip`, `CitationCard` (`rank` prop for `[n]`
markers), `AbstentionCard` (`topPassages`, rendered inline per-turn so an
older abstained turn keeps its own evidence record once a newer turn takes
over the latest-only citations panel). New: `Sidebar` (real conversation
list + corpus footer from `GET /documents`; a Library/Evals link pair
beyond the mockup's own scope — it has no way back to the rest of the app
at all, a real usability gap, not an open design question), `ChatHeader`,
`Composer`, `CitationsPanel`, `ExchangeCard`. `api.healthz()` added (+ a
`next.config.mjs` proxy rule, since `/healthz` lives outside `/api/v1`) so
the composer and run-detail panel show the real running τ_retrieval, not a
guess.

### Live verification — a real 3-turn conversation, real Groq

Scratchpad Playwright against the real API + real far-25 corpus, zero
console errors across every capture:

1. *"What does §25.1309(b) require for catastrophic failure conditions?"*
   → GROUNDED 0.9172, 1 citation, 49.2s. A fresh `/ask` session's URL
   silently became `/ask/55c8dcbd-…` (no page navigation happened).
2. *"What factor of safety does §25.303 prescribe?"* → GROUNDED 0.9989,
   §25.303's factor of safety of 1.5, 24.3s, same conversation URL.
3. *"What does DO-178C say about MC/DC coverage requirements?"* (real
   out-of-corpus must-abstain, zero extra Groq tokens — Gate A blocks
   before generation) → "No grounded answer," 6 closest passages, same
   conversation URL.

Sidebar picked up the new conversation with the correct summary:
`ABSTAINED · 3 turns` (the LATEST turn's status, not an aggregate — by
design). A hard reload of `/ask/55c8dcbd-…` correctly replayed the full
3-turn history from Postgres from a cold page load.

Screenshots: `docs/demo/chat/01_grounded_turn.png` (turn 1, live),
`docs/demo/chat/02_multi_turn_reload.png` (all 3 turns, after a cold
reload), `docs/demo/chat/03_abstained_closest_passages.png` (turn 3's
inline closest-passage cards + the matching right panel),
`docs/demo/chat/04_mobile_sidebar_overlay.png` (mobile, see below).

### Two real bugs found live, neither caught by `tsc`/`eslint`

1. **A replayed historical turn showed every pipeline-status dot as
   dim/pending even though the turn was long done.** `askToExchange()` set
   `stage: null` for loaded history, and `PipelineStatus`'s `reached = i <=
   currentIdx` is false for every step when `currentIdx` is `-1`. Fixed:
   derive a terminal stage from the persisted `status` instead — grounded
   → `"generating"` (all three reached); abstained → `"reranking"` (Gate A
   never lets an abstained turn reach `"generating"` at all, matching its
   real live behavior). Confirmed fixed on the same cold-reload screenshot
   (`02_multi_turn_reload.png`) that first caught it.
2. **Opening the sidebar on a narrow (<1100px) viewport pushed the chat
   column into an unusably narrow sliver instead of overlaying it.** The
   design handoff's own README specifies "sidebar defaults closed below
   1100px, toggle still works" but doesn't specify push-vs-overlay, and the
   mockup's in-flow push behavior — correct at desktop widths — breaks down
   completely on a real phone screen. Fixed: the sidebar becomes a fixed,
   full-height overlay with a tap-to-close backdrop below 1100px, keeping
   the mockup's push behavior unchanged at ≥1100px. Verified: opening,
   the underlying thread visibly dims and stays fully legible next to the
   overlay (`04_mobile_sidebar_overlay.png`); tapping the backdrop closes
   it again.

### A residual observed, not fixed (already named in the design, now confirmed live)

A replayed abstained turn's closest passages render as "—" in both the
inline card and the citations panel. `top_passages` is an SSE-only payload
(`Abstention.top_passages`) — it is never persisted to the `asks` table
(confirmed against `core/groundcite/services/ask.py`'s `_debug()` method,
which builds `pipeline_debug` from timings/counts/usage, never passages),
so a reloaded conversation genuinely cannot recover them; this was named as
an accepted gap in `docs/WEEK6_INSTRUCTIONS.md` before any code was
written, not discovered as a surprise. The confidence/threshold/latency in
"Run detail" still populate correctly on replay since those fields ARE
persisted (`ask.confidence`, `ask.latency_ms`).

### Gates, clean state

- **core**: `ruff check`/`ruff format --check` clean, `mypy --strict` clean
  in **both** install states (hid/restored the
  `openai`/`FlagEmbedding`/`rerankers` site-packages dirs + cleared
  `.mypy_cache`), `lint-imports` 5/5 kept, `pytest` — **211 passed**.
- **api**: `ruff check`/`ruff format --check` clean, `mypy app tests`
  clean, `pytest` — **66 passed** (unit) + **11 passed** (live-DB
  integration).
- **web**: `tsc --noEmit` clean, `eslint .` clean, `next build` clean
  (`/ask` static, `/ask/[conversationId]` dynamic — both resolve
  correctly).

CI confirmed green on every commit pushed this week (5 pushes, 3 jobs each
— core+db, api, web — all green): `8eae6e7`, `49d26e9`, `8c70aee`,
`7e2b66f`, `00a4971`.

## AD deviations from the instructions doc (stated, not silently forced)

None of the DECIDED architecture calls (AD-1 through AD-8) needed to change
to fit reality. Two implementation-level findings surfaced only by actually
running the system (the two bugs above) got fixed within the existing plan
rather than requiring a plan change — the plan's own "verify live in a
browser" gate is exactly what caught both.

## Residuals explicitly flagged (not fixed here — named in `docs/ROADMAP.md`)

1. **Inline `[n]` citation markers in the answer prose** — the generator's
   `answer_md` contract has never emitted them (confirmed in
   `core/groundcite/services/prompts/answerer.py`); building this needs a
   prompt change, its own rule-4-gated effort, not bundled into a redesign.
2. **A mobile (<1360px) citation sheet/popover** — the design handoff's own
   README says this wasn't built in the mock either; citations panel just
   hides below that width today, same as here.
3. **Conversation rename/delete** — not in the mockup's interaction list.
4. **Conversation title generation is literal, not summarized** — first
   ~80 chars of the opening question, no LLM call. A real, separate
   feature if ever wanted (cost + a prompt to design and verify).
5. **A replayed abstained turn's closest passages are unrecoverable**
   (`top_passages` is SSE-only, never persisted) — named above, a real
   gap in `Ask`'s persisted shape, not a chat-page bug.
6. Every Week 4/5 residual not touched by this week's phases stays
   flagged, unchanged, in `docs/ROADMAP.md`.

**Week 6 close-out summary**: `/ask` is now a real multi-turn chat
experience against the owner-supplied design — a titled, persisted
conversation groups turns that each still run the exact same independent
pipeline as before (spec §3.2 held throughout, verified by construction:
`core/groundcite/services/ask.py`'s diff this week is a tag threaded
through, not a logic change). Verified against a real 3-turn conversation
with real Groq calls and a real must-abstain question, across a cold reload
and a narrow mobile viewport, zero console errors anywhere. Both real bugs
found this week were found by actually looking at the running system, not
by reasoning about the code — one is fixed, the other (unrecoverable
replayed passages) is a real, named, and already-anticipated data gap, not
a surprise discovered too late to document honestly.
