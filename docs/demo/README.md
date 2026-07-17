# Week 5 demo capture (AD-6)

Recorded live against the real running app (`apps/api` on :8000, `apps/web`
on :3000) and the real far-25 corpus, via scratchpad Playwright
(`page.video()`), not staged or fabricated. Zero console errors throughout.

- **`demo.webm`** — the full spec §15 loop, ~1280×800, continuous capture:
  1. Ask *"What does §25.1309(b) require for catastrophic failure
     conditions?"* on `/ask` → streams to GROUNDED, confidence 0.9172, 3
     citations.
  2. Click the first citation card → lands on `/documents/far-25` with
     §25.1309(b) highlighted in the reader and its tree ancestors expanded.
  3. Back to `/ask`, ask *"What does DO-178C say about MC/DC coverage
     requirements?"* (out-of-corpus) → Gate A abstains before any LLM call
     (zero Groq tokens), `AbstentionCard` shows the reason (Week 5 AD-5), 6
     closest-passage cards.
  4. `/evals` → the runs table, the per-suite chart, an expanded per-case
     drill-down.
- **`frame_1_retrieving.png`** through **`frame_6_evals_drilldown.png`** —
  key frames extracted at each step above.
- **`evals_screenshot.png`** — the Phase 3 `/evals` full-page screenshot
  (the blog post's lead image).

**GIF conversion is an OWNER ACTION.** Neither `ffmpeg` nor `gifski` is
installed in this environment (verified: `which ffmpeg` / `which gifski`
both empty) — per Week 5 AD-6, the deliverable in that case is the webm +
key frames, not a fabricated or skipped GIF. Convert `demo.webm` to a GIF
(e.g. `ffmpeg -i demo.webm -vf "fps=12,scale=960:-1" demo.gif` or via
`gifski`) when one of those tools is available, for the published blog post.
