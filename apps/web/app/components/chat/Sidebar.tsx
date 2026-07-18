"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

function statusLine(latestStatus: string | null, turnCount: number | null): {
  text: string;
  className: string;
} {
  const turns = `${turnCount ?? 0} turn${turnCount === 1 ? "" : "s"}`;
  if (latestStatus === "grounded") return { text: `GROUNDED · ${turns}`, className: "text-grounded" };
  if (latestStatus === "abstained")
    return { text: `ABSTAINED · ${turns}`, className: "text-abstained" };
  return { text: turns, className: "text-ink/40" };
}

/**
 * Collapsible left sidebar (spec §2.2): wordmark, "+ New ask", the
 * conversation history list, a corpus footer sourced from real
 * `GET /documents` data (not hardcoded -- same single-document assumption
 * already tracked as GitHub issue #3, not a new gap), and a small
 * Library/Evals link pair. The mockup's own scope stops at the chat page
 * and has no way back to the rest of the app at all -- this pair is a
 * necessary addition beyond the literal design, not an open question.
 */
export function Sidebar({
  open,
  activeConversationId,
  corpusCode,
  chunkCount,
  tauRetrieval,
}: {
  open: boolean;
  activeConversationId: string | null;
  corpusCode: string | null;
  chunkCount: number | null;
  tauRetrieval: number | null;
}) {
  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: api.listConversations,
  });

  return (
    <aside
      className={
        // ≥1100px: in-flow, pushes the chat column (the mockup's own
        // behavior). <1100px: a real viewport is too narrow to push AND
        // still show a usable chat column, so the sidebar overlays instead
        // (fixed, full-height, above the content) -- the design handoff's
        // README only specifies "sidebar defaults closed below 1100px,
        // toggle still works," not push-vs-overlay; overlay is the one that
        // doesn't leave the chat squeezed into an unreadable sliver.
        "flex shrink-0 flex-col overflow-hidden whitespace-nowrap border-r border-line bg-panel transition-[width] duration-[250ms] ease-linear max-[1099px]:fixed max-[1099px]:inset-y-0 max-[1099px]:left-0 max-[1099px]:z-30 max-[1099px]:shadow-2xl " +
        (open ? "w-[264px]" : "w-0")
      }
    >
      <div className="flex items-center gap-[9px] px-5 pb-3.5 pt-[18px]">
        <span
          aria-hidden
          className="h-2 w-2 rounded-full bg-grounded shadow-[0_0_8px_rgba(28,122,77,0.5)]"
        />
        <span className="font-mono text-[13px] font-medium tracking-[0.2em] text-ink">
          GROUNDCITE
        </span>
      </div>

      <div className="px-3.5 pb-3 pt-1">
        <Link
          href="/ask"
          className="flex w-full items-center justify-center gap-2 rounded-md border border-accent/45 bg-accent/[0.06] px-3 py-2.5 font-serif text-[13px] font-medium text-accent transition-colors hover:bg-accent/[0.14]"
        >
          <span className="text-[15px] leading-none">+</span> New ask
        </Link>
      </div>

      <div className="px-5 pb-2 pt-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink/40">
        Recent
      </div>
      <nav aria-label="Conversations" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2">
        {(conversations ?? []).map((c) => {
          const active = c.id === activeConversationId;
          const status = statusLine(c.latest_status, c.turn_count);
          return (
            <Link
              key={c.id}
              href={`/ask/${encodeURIComponent(c.id)}`}
              className={
                "block rounded-md border px-3 py-2.5 " +
                (active
                  ? "border-accent/20 bg-accent/[0.08] text-ink"
                  : "border-transparent text-ink/75 hover:bg-ink/[0.04]")
              }
            >
              <div className="truncate font-serif text-[13px]">{c.title}</div>
              <div className={"mt-[3px] font-mono text-[10px] " + status.className}>
                {status.text}
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="flex gap-4 border-t border-line px-5 py-3 font-mono text-[10px] uppercase tracking-[0.1em] text-ink/45">
        <Link href="/library" className="hover:text-accent">
          Library
        </Link>
        <Link href="/evals" className="hover:text-accent">
          Evals
        </Link>
      </div>

      <div className="min-w-[224px] border-t border-line px-5 py-3.5">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink/40">
          Corpus
        </div>
        <div className="mt-1.5 text-xs text-ink/75">{corpusCode ?? "—"}</div>
        <div className="mt-0.5 font-mono text-[10px] text-ink/40">
          {chunkCount !== null ? `${chunkCount.toLocaleString()} chunks` : "…"}
          {tauRetrieval !== null ? ` · τ ${tauRetrieval.toFixed(2)}` : ""}
        </div>
      </div>
    </aside>
  );
}
