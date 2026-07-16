import type { Stage } from "@/lib/sse";

const STEPS: Stage[] = ["retrieving", "reranking", "generating"];

/**
 * A live readout of the actual pipeline stage (spec §7 STAGE events) --
 * not a decorative stepper, the three labels are the real `Stage` enum and
 * light up as the corresponding SSE event genuinely arrives. Skips straight
 * to done if Gate A abstains before "generating" is ever reached (spec §7:
 * abstention skips the generating stage entirely) -- this component just
 * reflects whatever stage state it's given, so that behavior falls out
 * naturally rather than needing special-casing here.
 */
export function PipelineStatus({
  currentStage,
  done,
}: {
  currentStage: Stage | null;
  done: boolean;
}) {
  const currentIdx = currentStage ? STEPS.indexOf(currentStage) : -1;

  return (
    <div
      role="status"
      aria-label="Pipeline status"
      className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-widest text-text/50"
    >
      {STEPS.map((step, i) => {
        // Reached means "a STAGE event for this step actually arrived" --
        // NOT "the stream is done". An abstained ask (Gate A) never reaches
        // "generating" at all, and the readout must show that honestly
        // rather than lighting every step once the terminal event lands.
        const reached = i <= currentIdx;
        const active = !done && i === currentIdx;
        return (
          <span key={step} className="flex items-center gap-1">
            {i > 0 && <span className="mx-1 text-border">/</span>}
            <span
              aria-hidden
              className={
                "h-1.5 w-1.5 rounded-full transition-colors " +
                (reached ? "bg-link" : "bg-border") +
                (active ? " animate-pulse" : "")
              }
            />
            <span className={reached ? "text-text/80" : undefined}>{step}</span>
          </span>
        );
      })}
    </div>
  );
}
