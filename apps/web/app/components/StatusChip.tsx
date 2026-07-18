/** GROUNDED/ABSTAINED status chip + retrieval confidence (spec §2.2, §10). */
export function StatusChip({
  status,
  confidence,
}: {
  status: "grounded" | "abstained";
  confidence: number | null;
}) {
  const grounded = status === "grounded";
  return (
    <span
      className={
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium tracking-wide " +
        (grounded
          ? "border-chat-grounded/40 bg-chat-grounded/10 text-chat-grounded"
          : "border-chat-abstained/40 bg-chat-abstained/10 text-chat-abstained")
      }
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {grounded ? "GROUNDED" : "ABSTAINED"}
      {confidence !== null && (
        <span className="font-mono opacity-80">{confidence.toFixed(4)}</span>
      )}
    </span>
  );
}
