import type { AbstentionReason } from "@/lib/sse";
import { CitationCard } from "./CitationCard";

/** Calm, aviation-flavored §2.2 copy for WHY the gate abstained -- named after
 * the gate that actually fired (spec §7 pipeline step 4/6), not a vaguer
 * "something went wrong". Additive detail under the spec-locked title/subtitle
 * below, never a replacement for them. */
const REASON_COPY: Record<AbstentionReason, string> = {
  weak_retrieval:
    "Gate A: no clause in the corpus scored above the retrieval confidence threshold — nothing retrieved was close enough to answer from.",
  uncited:
    "Gate B: the generated answer couldn't be traced back to specific clauses, even after one repair retry — withheld rather than risk an ungrounded claim.",
};

interface TopPassage {
  chunkId: string;
  clausePath: string;
  score: number;
  snippet: string;
}

interface AbstentionCardProps {
  reason?: AbstentionReason;
  /** Week 6: rendered as mini cards inside the card itself, not only in the
   * (latest-answer-only) citations panel -- a multi-turn thread needs each
   * past abstained turn to keep its own evidence record once a newer turn
   * has taken over the side panel. */
  topPassages?: TopPassage[];
  documentSlug?: string;
}

/**
 * Abstention is a first-class result, not an error (spec §7). Title/subtitle
 * copy is exact per spec §2.2 -- calm, never cute: "No grounded answer" /
 * "Confidence below threshold — closest passages shown below." `reason`
 * (Week 5 AD-5) adds one more calm line naming the gate that actually fired,
 * so the user sees WHY, not just that it abstained.
 */
export function AbstentionCard({ reason, topPassages, documentSlug }: AbstentionCardProps) {
  return (
    <div className="rounded-xl border border-abstained/25 bg-abstained/[0.04] p-5">
      <h2 className="text-[15px] font-semibold text-ink">No grounded answer</h2>
      <p className="mt-1 text-[13.5px] text-ink/60">
        Confidence below threshold — closest passages shown below.
      </p>
      {reason && <p className="mt-2 text-xs text-ink/45">{REASON_COPY[reason]}</p>}
      {topPassages && topPassages.length > 0 && (
        <div className="mt-3.5 flex flex-col gap-1.5">
          {topPassages.map((p, i) => (
            <CitationCard
              key={p.chunkId}
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
    </div>
  );
}
