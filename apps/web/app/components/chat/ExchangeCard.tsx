import type { Exchange } from "@/lib/chatExchange";
import { renderAnswerMd } from "@/lib/markdown";
import { AbstentionCard } from "@/app/components/AbstentionCard";
import { PipelineStatus } from "@/app/components/PipelineStatus";
import { StatusChip } from "@/app/components/StatusChip";

/**
 * One full chat turn (Week 6, spec §2.2.1): the user's question, the live
 * pipeline-status row (the honesty signal, spec §7 -- always shown, not
 * just while streaming), then the grounded answer or the abstention card.
 * Renders identically whether `exchange` is currently streaming or was
 * loaded from a past conversation (`lib/chatExchange.ts` normalizes both
 * into the same shape).
 */
export function ExchangeCard({
  exchange,
  documentSlug,
}: {
  exchange: Exchange;
  documentSlug?: string;
}) {
  const done = !exchange.streaming;

  return (
    <div className="flex flex-col gap-[28px]">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[12px_12px_3px_12px] border border-chat-line-user bg-chat-bubble px-4 py-3 font-serif text-sm leading-[1.55] text-chat-ink">
          {exchange.question}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <PipelineStatus currentStage={exchange.stage} done={done} />

        {exchange.status === "error" && (
          <div className="rounded-xl border border-chat-abstained/25 bg-chat-abstained/[0.04] p-5">
            <h2 className="text-[15px] font-semibold text-chat-ink">Something went wrong</h2>
            <p className="mt-1 text-[13.5px] text-chat-ink/60">{exchange.errorMessage}</p>
          </div>
        )}

        {exchange.status === "abstained" && (
          <AbstentionCard
            reason={exchange.abstentionReason ?? undefined}
            documentSlug={documentSlug}
            topPassages={exchange.topPassages.map((p) => ({
              chunkId: p.chunk_id,
              clausePath: p.clause_path,
              score: p.score,
              snippet: p.content,
            }))}
          />
        )}

        {(exchange.streaming || exchange.status === "grounded") && exchange.answerMd && (
          <div className="rounded-xl border border-chat-line-card bg-chat-card px-[22px] py-5">
            {exchange.status === "grounded" && (
              <div className="mb-3.5">
                <StatusChip status="grounded" confidence={exchange.confidence} />
              </div>
            )}
            <div className="whitespace-pre-wrap font-serif text-[14.5px] leading-[1.65] text-chat-ink/90">
              {renderAnswerMd(exchange.answerMd)}
              {exchange.streaming && (
                <span
                  aria-hidden
                  className="ml-0.5 inline-block h-[15px] w-2 animate-pulse bg-chat-accent align-text-bottom"
                />
              )}
            </div>
            {exchange.status === "grounded" && (
              <div className="mt-4 flex gap-3.5 border-t border-chat-line pt-3 font-mono text-[10px] text-chat-ink/35">
                <span>
                  {exchange.citations.length} citation{exchange.citations.length === 1 ? "" : "s"}
                </span>
                {exchange.latencyMs !== null && (
                  <span>{(exchange.latencyMs / 1000).toFixed(1)}s</span>
                )}
                {exchange.askId && <span>ask_{exchange.askId.slice(0, 8)}</span>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Latest exchange's citations or closest passages, for the right panel
 * (spec §10 "Citations · latest answer" -- panel only ever reflects the
 * most recent turn, unlike the inline per-turn cards above). */
export function latestPassages(
  exchange: Exchange | undefined,
): { chunkId: string; clausePath: string; score: number; snippet: string }[] {
  if (!exchange) return [];
  if (exchange.status === "grounded") {
    return exchange.citations.map((c) => ({
      chunkId: c.chunk_id,
      clausePath: c.clause_path ?? "",
      score: c.score,
      snippet: c.claim ?? "",
    }));
  }
  if (exchange.status === "abstained") {
    return exchange.topPassages.map((p) => ({
      chunkId: p.chunk_id,
      clausePath: p.clause_path,
      score: p.score,
      snippet: p.content,
    }));
  }
  return [];
}
