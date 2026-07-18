# Handoff: GroundCite Chat Redesign

## Overview
A redesign of GroundCite's `/ask` page into a multi-turn AI chat experience. GroundCite is a grounded Q&A system over aerospace & engineering standards (14 CFR Part 25, etc.) — every answer carries verifiable clause citations, or the system abstains. The redesign keeps the product's honesty signals (per-message pipeline status, GROUNDED/ABSTAINED chips, retrieval confidence scores) while moving from one-shot Q&A to a conversation model with history.

Target codebase: `apps/web` — Next.js (App Router) + Tailwind + TanStack Query, with an SSE streaming hook in `lib/sse.ts`.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, not production code to copy directly. The task is to **recreate this design in the existing Next.js/Tailwind codebase** using its established patterns: the existing `useAskStream` SSE hook, `PipelineStatus`, `StatusChip`, `CitationCard`, and `AbstentionCard` components map 1:1 onto pieces of this design and should be restyled/extended rather than rewritten from scratch.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and interactions are final. Recreate pixel-perfectly.

## Layout — App Shell
Full-viewport 3-column flex row (`height: 100vh; overflow: hidden`):

1. **Left sidebar** — 264px, collapsible to 0 (`transition: width 0.25s ease; overflow: hidden; white-space: nowrap`). Background `#E9E6DC`, right border `1px solid #DCD8CA`.
2. **Chat column** — `flex: 1; min-width: 0`, column flex: sticky header, scrollable thread, fixed composer. Page background `#F0EEE6`.
3. **Right citations panel** — 320px, background `#E9E6DC`, left border `1px solid #DCD8CA`. Hidden below 1360px viewport width (media query).

Thread and composer content constrained to `max-width: 768px; margin: 0 auto`.

## Design Tokens

### Colors
| Token | Value | Use |
|---|---|---|
| bg-page | `#F0EEE6` | app background |
| bg-panel | `#E9E6DC` | sidebars |
| bg-card | `#FDFCF8` | answer cards, citation cards |
| bg-composer | `#FFFFFF` | input field container |
| bg-user-bubble | `#E7E0CF` | user messages |
| border | `#DCD8CA` | panel borders, dividers |
| border-card | `#E2DED0` | card borders |
| border-dim | `#CFC9B9` | subtle borders, separators |
| border-user | `#E0D9C7` | user bubble border |
| text | `#2B2A24` | primary text |
| text-muted | `rgba(60,55,45,α)` | α 0.75/0.6/0.45/0.38/0.3 tiers |
| accent | `#C15F3C` | links, citation markers, primary button, active nav |
| accent-hover | `#A94F32` | hover state |
| accent-tint | `rgba(193,95,60,α)` | α 0.06–0.18 backgrounds, 0.45 borders |
| grounded | `#1C7A4D` | GROUNDED chip, status dot (`rgba(28,122,77,0.1)` bg, `0.4` border) |
| abstained | `#A16207` | ABSTAINED chip (`rgba(161,98,7,0.04–0.1)` bg, `0.25–0.4` border) |
| header-bg | `rgba(250,249,245,0.92)` + `backdrop-filter: blur(8px)` | sticky header |

### Typography
- **Body/serif**: `'Source Serif 4', Georgia, serif` (Google Fonts, opsz 8..60, weights 400/500/600) — all prose, questions, answers, headings.
- **Mono**: `'JetBrains Mono', monospace` (400/500/600) — wordmark, pipeline stages, chips' scores, clause paths (§25.1309), metadata, section labels.
- Scale: answer text 14.5px/1.65; user bubble & inputs 14px/1.55; h1 header 14px/600; sidebar items 13px; chips 11px; mono metadata 10–11px; section labels 10px uppercase, `letter-spacing: 0.14em`; wordmark 13px, `letter-spacing: 0.2em`.

### Radii & spacing
- Cards 12px; sidebar items & recent-passage cards 6px; citation cards 8px; composer 10px; buttons 6–7px; chips/badges 9999px.
- Message gap 28px; card padding 20px 22px; panel padding 20px; composer padding `6px 6px 6px 16px`.

## Screens / Components

### Left sidebar (collapsible)
- **Wordmark row**: green dot 8px (`#1C7A4D`, glow `box-shadow: 0 0 8px rgba(28,122,77,0.5)`) + `GROUNDCITE` mono 13px/500.
- **"+ New ask" button**: full-width, accent outline style — border `1px solid rgba(193,95,60,0.45)`, bg `rgba(193,95,60,0.06)`, text `#C15F3C` 13px/500, hover bg `rgba(193,95,60,0.14)`. Clears the thread.
- **"Recent" label**: mono 10px uppercase, muted 0.38.
- **Conversation list**: each item = title (13px, ellipsis) + status line (mono 10px: `GROUNDED · 2 turns` in green, or `ABSTAINED · 1 turn` in ochre, or muted). Active item: bg `rgba(193,95,60,0.08)`, border `rgba(193,95,60,0.18)`. Hover: `rgba(60,55,45,0.04)`.
- **Corpus footer** (border-top, `min-width: 224px` so it doesn't squash during collapse animation): label "Corpus", value "14 CFR Part 25", meta "1,412 chunks · τ 0.70".
- **Collapse behavior**: hamburger button in chat header toggles width 264px ↔ 0px. Default open ≥1100px viewport, closed below.

### Chat header (sticky)
- Hamburger (30×30, 3 bars 1.5px, border `#DCD8CA`, hover `rgba(60,55,45,0.06)`) + conversation title (h1 14px/600, ellipsis) + corpus pill (mono 10px, `border: 1px solid #CFC9B9`, radius 9999px, padding 3px 10px).
- Right: tagline "every answer cites — or abstains" (mono 10px, muted 0.38, truncates; hidden <1360px).

### Message thread
- **User message**: right-aligned bubble, `max-width: 85%`, radius `12px 12px 3px 12px`, bg `#E7E0CF`, border `#E0D9C7`, padding 12px 16px.
- **Pipeline status row** (above each assistant answer, always visible — honesty signal): mono 10px uppercase, `retrieving / reranking / generating` separated by `/` in border-dim color, each stage a 5px dot + label. States: done = accent dot, full opacity; active = accent dot with 1s pulse animation (`opacity 1↔0.35`); pending = dim dot (`#CFC9B9`), 0.4 opacity. Optional `· 3.2s` latency suffix. Row wraps (`flex-wrap: wrap`).
- **Grounded answer card**: bg-card, border-card, radius 12px, padding 20px 22px. Contains:
  - GROUNDED chip: pill, green scheme, 11px/500, dot + `GROUNDED` + mono confidence score (e.g. `0.8412`).
  - Answer prose 14.5px/1.65, `**bold**` for clause refs and key terms; inline citation markers `[1]` as `<sup>` — mono 10px, accent color, clickable (scrolls/highlights the matching card in the citations panel).
  - Footer row (border-top `#DCD8CA`, mono 10px, muted 0.35): `3 citations · 1,204 tokens · ask_9f2c81`.
- **Abstention card**: same shape but bg `rgba(161,98,7,0.04)`, border `rgba(161,98,7,0.25)`. ABSTAINED chip (ochre) + score, heading "No grounded answer" (15px/600), subline "Confidence below threshold — closest passages shown below." (13.5px muted), gate explanation (12px, muted 0.45), then closest-passage mini-cards: bg-card, radius 6px, clause path + score (mono 11px) and one-line ellipsized excerpt (12px).
- **Streaming state**: text streams word-by-word with a blinking caret (8×15px accent block, `1s step-end` blink). Chip appears only when generation completes.

### Composer (fixed bottom)
- Container: border-top on `#E9E6DC` strip. Form: radius 10px, border `#E0D9C7`, bg white; text input transparent/borderless 14px; Send button: bg `#C15F3C`, text `#F0EEE6`, 13px/600, radius 7px, padding 9px 18px, hover `#A94F32`.
- Below: centered mono 10px muted 0.3 caption: `answers carry verifiable clause citations — or the system abstains · τ_retrieval 0.70`.

### Citations panel (right)
- Label `CITATIONS · LATEST ANSWER` (mono 10px uppercase).
- Citation cards (one per `[n]` marker): header row `[1] §25.1309(b)(1)` (mono 11px accent) + score (mono 11px muted); excerpt 12px/1.55 muted, 4-line clamp; footer `14 CFR Part 25 · Subpart F` (mono 10px muted 0.3). Hover: border → `rgba(193,95,60,0.5)`. Click → clause reader.
- **Run detail** section (border-top): 2-col grid, 12px — Retrieval confidence (green mono), Threshold τ, Chunks reranked (`24 → 8`), Latency.

## Interactions & Behavior
- Submit (Enter or Send): append user bubble, clear input, scroll to bottom; pipeline advances retrieving → reranking (~0.9s) → generating (~1.8s) — in production, drive from the real SSE `stage` events in `lib/sse.ts`.
- Streaming tokens append to the answer; auto-scroll thread to bottom on each token.
- Sidebar toggle animates width 0.25s ease.
- Citation `[n]` click: highlight matching card in right panel.
- Reduced motion: all animations disabled via `prefers-reduced-motion`.
- Custom scrollbar: 8px, thumb `#CFC9B9`, radius 4px.

## State Management
- `conversations[]` (id, title, status, turnCount) — sidebar list.
- `exchanges[]` per conversation: `{ question, stage: 0-3, text, citations[], status, confidence }`.
- `input`, `sidebarOpen` (default `innerWidth >= 1100`).
- Latest answer's citations feed the right panel.
- Data: existing `useAskStream` hook; conversation persistence is new backend work (not covered by current one-shot `/ask` API).

## Responsive
- <1360px: hide right citations panel and header tagline (citations should then be reachable inline — e.g. tapping `[n]` opens a sheet/popover; not built in the mock).
- <1100px: sidebar defaults closed; toggle still works.

## Assets
None — no images or icon fonts. The hamburger is 3 CSS bars; dots/chips are pure CSS. Fonts from Google Fonts: Source Serif 4, JetBrains Mono.

## Files
- `GroundCite Chat.dc.html` — the hi-fi design (warm light theme, final). Open in a browser; the composer simulates the full pipeline + streaming flow.
- `GroundCite Chat -dark-.dc.html` — earlier dark "mission control" variant, reference only.
- `GroundCite Ask (current).dc.html` — recreation of the current production `/ask` page, for before/after comparison.
- `support.js` — runtime the design files need to render; not part of the design.

## Suggested Tailwind token mapping
```ts
colors: {
  bg: "#F0EEE6", panel: "#E9E6DC", card: "#FDFCF8",
  ink: "#2B2A24", line: "#DCD8CA", "line-dim": "#CFC9B9",
  accent: { DEFAULT: "#C15F3C", hover: "#A94F32" },
  grounded: "#1C7A4D", abstained: "#A16207",
}
fontFamily: {
  serif: ["'Source Serif 4'", "Georgia", "serif"],
  mono: ["'JetBrains Mono'", "monospace"],
}
```
