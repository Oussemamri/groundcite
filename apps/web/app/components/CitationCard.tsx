import Link from "next/link";

interface CardProps {
  clausePath: string;
  chunkId: string;
  score: number;
  snippet: string;
  documentSlug?: string;
  /** [n] marker (spec §10, Week 6 chat theme) -- the citation's rank, or the
   * closest-passage's array position. Omitted renders no marker (used
   * outside the chat theme's numbered-citation convention). */
  rank?: number;
}

/**
 * One citation or closest-passage card (spec §10: "clause_path mono,
 * snippet, score"). Links into the reader, deep-linked to the exact chunk
 * (spec §7/§10: "clicking a citation opens the reader anchored &
 * highlighted") -- documentSlug is optional because the ask stream doesn't
 * carry it; when absent the card still shows the clause/score/snippet, just
 * without a working reader link (falls back gracefully, not silently wrong).
 */
export function CitationCard({
  clausePath,
  chunkId,
  score,
  snippet,
  documentSlug,
  rank,
}: CardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-accent">
          {rank !== undefined ? `[${rank}] ` : ""}
          {clausePath}
        </span>
        <span className="font-mono text-[11px] text-ink/40">{score.toFixed(4)}</span>
      </div>
      <p className="mt-1.5 line-clamp-4 text-xs leading-[1.55] text-ink/60">{snippet}</p>
    </>
  );

  if (!documentSlug) {
    return <div className="rounded-lg border border-line-card bg-card p-3">{body}</div>;
  }

  return (
    <Link
      href={`/documents/${encodeURIComponent(documentSlug)}?chunk=${encodeURIComponent(chunkId)}`}
      className="block rounded-lg border border-line-card bg-card p-3 transition-colors hover:border-accent/50"
    >
      {body}
    </Link>
  );
}
