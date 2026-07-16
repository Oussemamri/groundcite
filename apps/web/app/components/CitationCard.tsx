import Link from "next/link";

interface CardProps {
  clausePath: string;
  chunkId: string;
  score: number;
  snippet: string;
  documentSlug?: string;
}

/**
 * One citation or closest-passage card (spec §10: "clause_path mono,
 * snippet, score"). Links into the reader, deep-linked to the exact chunk
 * (spec §7/§10: "clicking a citation opens the reader anchored &
 * highlighted") -- documentSlug is optional because the ask stream doesn't
 * carry it; when absent the card still shows the clause/score/snippet, just
 * without a working reader link (falls back gracefully, not silently wrong).
 */
export function CitationCard({ clausePath, chunkId, score, snippet, documentSlug }: CardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-text">{clausePath}</span>
        <span className="font-mono text-xs text-text/50">{score.toFixed(4)}</span>
      </div>
      <p className="mt-1.5 line-clamp-3 text-xs text-text/60">{snippet}</p>
    </>
  );

  if (!documentSlug) {
    return <div className="rounded border border-border bg-surface p-3">{body}</div>;
  }

  return (
    <Link
      href={`/documents/${encodeURIComponent(documentSlug)}?chunk=${encodeURIComponent(chunkId)}`}
      className="block rounded border border-border bg-surface p-3 transition-colors hover:border-link/50"
    >
      {body}
    </Link>
  );
}
