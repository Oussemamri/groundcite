import { CitationCard } from "@/app/components/CitationCard";
import { latestPassages } from "./ExchangeCard";
import type { Exchange } from "@/lib/chatExchange";

/**
 * Right panel (spec §10, §2.2.1): the LATEST turn's citations or closest
 * passages -- older turns keep their own permanent record inline via
 * `ExchangeCard`'s `AbstentionCard`/citation footer, this panel is
 * deliberately latest-only ("Citations · latest answer", not a full-thread
 * citation index). Hidden below 1360px (spec: citations should then be
 * reachable inline -- e.g. tapping [n] opens a sheet; not built here, see
 * Week 6 AD-8 / docs/ROADMAP.md).
 */
export function CitationsPanel({
  latest,
  documentSlug,
  tauRetrieval,
}: {
  latest: Exchange | undefined;
  documentSlug?: string;
  tauRetrieval: number | null;
}) {
  const passages = latestPassages(latest);
  const label = latest?.status === "abstained" ? "Closest passages" : "Citations";
  const showRunDetail = latest && (latest.status === "grounded" || latest.status === "abstained");

  return (
    <aside className="hidden w-[320px] shrink-0 overflow-y-auto border-l border-chat-line bg-chat-panel p-5 min-[1360px]:block">
      <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-chat-ink/45">
        {label} · latest answer
      </h2>
      {passages.length === 0 ? (
        <p className="mt-3 text-xs text-chat-ink/35">
          {latest ? "—" : "Citations will appear here."}
        </p>
      ) : (
        <div className="mt-3.5 flex flex-col gap-2">
          {passages.map((p, i) => (
            <CitationCard
              key={`${p.chunkId}-${i}`}
              rank={i + 1}
              chunkId={p.chunkId}
              clausePath={p.clausePath}
              score={p.score}
              snippet={p.snippet}
              documentSlug={documentSlug}
            />
          ))}
        </div>
      )}

      {showRunDetail && latest && (
        <div className="mt-5 border-t border-chat-line pt-4">
          <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-chat-ink/45">
            Run detail
          </h2>
          <div className="mt-2.5 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-xs text-chat-ink/60">
            <span>Retrieval confidence</span>
            <span
              className={
                "font-mono " + (latest.status === "grounded" ? "text-chat-grounded" : "")
              }
            >
              {latest.confidence !== null ? latest.confidence.toFixed(4) : "—"}
            </span>
            <span>Threshold τ</span>
            <span className="font-mono">
              {tauRetrieval !== null ? tauRetrieval.toFixed(2) : "—"}
            </span>
            {latest.latencyMs !== null && (
              <>
                <span>Latency</span>
                <span className="font-mono">{(latest.latencyMs / 1000).toFixed(1)}s</span>
              </>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
