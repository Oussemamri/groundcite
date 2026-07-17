# `apps/web/` — Next.js 15 App Router, TS strict, TanStack Query, Tailwind

Supplements the root [`CLAUDE.md`](../../CLAUDE.md) and
[`GROUNDCITE_PROJECT_SPEC.md`](../../GROUNDCITE_PROJECT_SPEC.md) — read those
first; this file only adds what's specific to working inside `apps/web/`.

## Gate commands (run before every commit that touches this directory)

```bash
cd apps/web
npm run typecheck    # tsc --noEmit
npm run lint         # eslint .  (NOT `next lint` — deprecated, see gotcha)
npm run build         # next build
```

`npm install` (not `uv sync` — this is the one non-Python workspace).
`package-lock.json` is committed; CI uses `npm ci`.

**Gotcha:** `next lint` is deprecated on this Next.js version and hangs on an
uncompleted interactive ESLint setup wizard if ever invoked directly — always
use `npm run lint` (→ `eslint .` via the hand-scaffolded `eslint.config.mjs`).

## Rules specific to this directory

- **TanStack Query for ALL server state** (root rule 6) — `useQuery` for
  documents/document/chunk/jobs/eval runs, no manual `useEffect` fetching.
  The one deliberate exception is the ask SSE stream (`lib/sse.ts`'s
  `useAskStream`): it's a `ReadableStream`, not a request/response fetch, so
  it's a hand-rolled hook, not a TanStack query. Don't build a second
  exception without a reason as good as that one.
- **No `any`, TS strict.** Response types in `lib/api.ts` mirror
  `apps/api/app/models.py` field-for-field — change both in the same commit,
  never let them drift (root rule 6). SSE event types in `lib/sse.ts` mirror
  the core `AskEventType`/`Stage` enums exactly (spec §7: one enum shared by
  API and web).
- **Every clause ID, standard code, and score renders in `font-mono`**
  (spec §2.2's signature detail) — audit for this on any new component that
  shows one. `.clause-id` / `.standard-code` are the existing global classes
  (`globals.css`); `font-mono` inline is equally fine for one-off spots
  (`clause_path`, scores) — both are used across the codebase already.
- **No component libraries, no axios/swr** (root rule 11 spirit) —
  Tailwind + `fetch` + TanStack Query, plus whichever single charting lib the
  active week's instructions doc names (spec §11 gets a row before first use,
  same as any new core dependency).
- **No secrets in this app, ever** (root rule 9) — it talks only to
  `/api/v1/*` via the `next.config.mjs` rewrite proxy (`API_ORIGIN`, default
  `localhost:8000`). If a feature seems to need a provider key on the web
  side, that's a sign it belongs in `apps/api` instead.
- **Verify in an actual browser before calling a UI change done**
  (root CLAUDE.md's explicit instruction) — `tsc`/`eslint`/`next build`
  passing is necessary, not sufficient; every real UI bug found in this repo
  so far was caught by actually looking at a live screenshot, never by the
  type checker. `chromium-cli` is not available in this Windows environment;
  the established fallback is Playwright installed in the session's
  scratchpad directory (NOT a project dependency — don't add it to
  `package.json`) driving the real dev server against the real API and the
  real corpus. Screenshot the golden path AND at least one edge case
  (mobile viewport, keyboard focus, an error/abstained state) — check for
  console errors every time.
- **Prefers-reduced-motion**: any new `animate-pulse`/animation usage needs
  a `prefers-reduced-motion: reduce` override in `globals.css` (accessibility
  quality floor, not spec-mandated but expected — see the existing block).
