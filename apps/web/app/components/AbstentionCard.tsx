/**
 * Abstention is a first-class result, not an error (spec §7). Copy is
 * exact per spec §2.2 -- calm, never cute: "No grounded answer" /
 * "Confidence below threshold — closest passages shown below."
 */
export function AbstentionCard() {
  return (
    <div className="rounded-lg border border-abstained/30 bg-abstained/5 p-5">
      <h2 className="text-base font-semibold text-text">No grounded answer</h2>
      <p className="mt-1 text-sm text-text/60">
        Confidence below threshold — closest passages shown below.
      </p>
    </div>
  );
}
