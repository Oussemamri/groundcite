import type { AbstentionReason } from "@/lib/sse";

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

interface AbstentionCardProps {
  reason?: AbstentionReason;
}

/**
 * Abstention is a first-class result, not an error (spec §7). Title/subtitle
 * copy is exact per spec §2.2 -- calm, never cute: "No grounded answer" /
 * "Confidence below threshold — closest passages shown below." `reason`
 * (Week 5 AD-5) adds one more calm line naming the gate that actually fired,
 * so the user sees WHY, not just that it abstained.
 */
export function AbstentionCard({ reason }: AbstentionCardProps) {
  return (
    <div className="rounded-lg border border-abstained/30 bg-abstained/5 p-5">
      <h2 className="text-base font-semibold text-text">No grounded answer</h2>
      <p className="mt-1 text-sm text-text/60">
        Confidence below threshold — closest passages shown below.
      </p>
      {reason && <p className="mt-2 text-xs text-text/50">{REASON_COPY[reason]}</p>}
    </div>
  );
}
