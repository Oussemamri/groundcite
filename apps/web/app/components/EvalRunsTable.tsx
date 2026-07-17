"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EvalRunOut } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;
}

/**
 * One runs-table row. Aggregates (abstention accuracy / mean citation
 * precision / recall@5) live only on the run-DETAIL response, not the list
 * response (rule 4: computed from persisted per-case rows, not a summary
 * column on eval_runs) -- so each row fetches its own detail, same
 * established pattern as `/library`'s `DocumentRow` (per-row fetch, cheap at
 * this corpus size: 13 runs, not 1,300).
 */
function EvalRunRow({
  run,
  selected,
  onSelect,
}: {
  run: EvalRunOut;
  selected: boolean;
  onSelect: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["evalRun", run.id],
    queryFn: () => api.getEvalRun(run.id),
  });
  const agg = data?.aggregates;
  const config = run.config;
  const tau = typeof config.tau_retrieval === "number" ? config.tau_retrieval.toFixed(2) : "—";
  // Every persisted run is a FULL run (AD-1 -- retrieval-only runs are never
  // persisted at all), but older git_shas' config snapshots predate the
  // groq_model key; llm_provider is present on all of them, so fall back to
  // that rather than mislabeling a real full run "retrieval-only".
  const model =
    typeof config.groq_model === "string"
      ? config.groq_model
      : typeof config.llm_provider === "string"
        ? config.llm_provider
        : "—";

  return (
    <tr
      onClick={onSelect}
      aria-selected={selected}
      className={
        "cursor-pointer border-b border-border last:border-0 " +
        (selected ? "bg-link/10" : "hover:bg-surface/60")
      }
    >
      <td className="py-3 pr-4 text-text">{run.suite ?? "—"}</td>
      <td className="py-3 pr-4 font-mono text-xs text-text/70">{run.git_sha}</td>
      <td className="py-3 pr-4 text-xs text-text/60">{formatDate(run.started_at)}</td>
      <td className="py-3 pr-4 font-mono text-xs text-text/70">{tau}</td>
      <td className="py-3 pr-4 font-mono text-xs text-text/60">{model}</td>
      <td className="py-3 pr-4 font-mono text-xs text-text/70">
        {agg ? formatPct(agg.abstention_accuracy) : "…"}
      </td>
      <td className="py-3 pr-4 font-mono text-xs text-text/70">
        {agg ? formatPct(agg.mean_citation_precision) : "…"}
      </td>
      <td className="py-3 font-mono text-xs text-text/70">
        {agg ? formatPct(agg.mean_recall_at_5) : "…"}
      </td>
    </tr>
  );
}

export function EvalRunsTable({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: EvalRunOut[];
  selectedRunId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <table className="w-full min-w-[820px] border-collapse text-sm">
      <thead>
        <tr className="border-b border-border text-left text-xs uppercase tracking-widest text-text/40">
          <th className="pb-2 pr-4 font-medium">Suite</th>
          <th className="pb-2 pr-4 font-medium">Git SHA</th>
          <th className="pb-2 pr-4 font-medium">Date</th>
          <th className="pb-2 pr-4 font-medium">τ</th>
          <th className="pb-2 pr-4 font-medium">Model</th>
          <th className="pb-2 pr-4 font-medium">Abstention acc.</th>
          <th className="pb-2 pr-4 font-medium">Citation prec.</th>
          <th className="pb-2 font-medium">Recall@5</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <EvalRunRow
            key={run.id}
            run={run}
            selected={run.id === selectedRunId}
            onSelect={() => onSelect(run.id)}
          />
        ))}
      </tbody>
    </table>
  );
}
