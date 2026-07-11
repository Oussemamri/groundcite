# groundcite-web

Next.js 15 (App Router, TS strict, TanStack Query, Tailwind) UI for GroundCite —
pages: `/ask`, `/library`, `/documents/[slug]`, `/evals` (spec §10).

P5 ships the shell only: the "mission control" theme tokens live in
[`tailwind.config.ts`](tailwind.config.ts) (spec §2.2) and the SSE event contract
in [`lib/sse.ts`](lib/sse.ts) mirrors the core enum (spec §7). Streaming, citation
cards, and the eval dashboard land in Weeks 4–5.

```bash
npm install
npm run dev        # http://localhost:3000
```
