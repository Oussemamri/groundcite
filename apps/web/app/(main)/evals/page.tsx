"use client";

/**
 * /evals — runs table + per-suite metric chart (recharts) + per-case
 * drill-down (spec §10; Week 5). This page is the screenshot for the blog
 * post.
 *
 * AD-1: reads persisted FULL-pipeline eval Runs only -- retrieval-only runs
 * are never persisted (spec §15.1), so there is no retrieval-only trend to
 * show here by design, not by omission. The page never triggers a run
 * (`POST /eval/runs` exists but is out of scope; this page is strictly
 * read-only over what's already in the database).
 *
 * AD-3: the per-case drill-down shows EXPECTED vs CITED clauses + the stored
 * metric numbers, not a literal retrieved top-k -- that ranked list isn't
 * persisted for FULL runs (only the recall@k NUMBERS and what got CITED
 * are). This is the honest reading of "retrieved-vs-expected" over the data
 * that actually exists.
 *
 * AD-4: the chart is a per-suite grouped bar of the three headline metrics
 * for each suite's LATEST run, each bar's git_sha named in the tooltip --
 * not a cross-config time series, since the four tracked git_shas differ in
 * τ_retrieval and model and a connecting line would imply a false
 * comparability.
 */

import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EvalRunOut } from "@/lib/api";
import { EvalRunsTable } from "@/app/components/EvalRunsTable";
import { EvalsChart, type SuiteBaseline } from "@/app/components/EvalsChart";
import { EvalCaseDrilldown } from "@/app/components/EvalCaseDrilldown";

/** Newest run per suite, in first-seen (= newest, since the API returns runs
 * newest-first) order -- the chart's "latest comparable baseline" set. */
function latestRunPerSuite(runs: EvalRunOut[]): EvalRunOut[] {
  const seen = new Map<string, EvalRunOut>();
  for (const run of runs) {
    const suite = run.suite ?? "unknown";
    if (!seen.has(suite)) seen.set(suite, run);
  }
  return [...seen.values()];
}

function EvalsChartSection({ runs }: { runs: EvalRunOut[] }) {
  const latest = useMemo(() => latestRunPerSuite(runs), [runs]);
  const detailQueries = useQueries({
    queries: latest.map((run) => ({
      queryKey: ["evalRun", run.id],
      queryFn: () => api.getEvalRun(run.id),
    })),
  });

  const loaded = detailQueries.every((q) => q.data);
  if (!loaded) {
    return <p className="text-sm text-ink/40">Loading chart…</p>;
  }

  const data: SuiteBaseline[] = detailQueries.map((q, i) => ({
    suite: latest[i]?.suite ?? "unknown",
    git_sha: latest[i]?.git_sha ?? "unknown",
    recall_at_5: q.data?.aggregates.mean_recall_at_5 ?? null,
    mean_citation_precision: q.data?.aggregates.mean_citation_precision ?? null,
    abstention_accuracy: q.data?.aggregates.abstention_accuracy ?? null,
  }));

  return <EvalsChart data={data} />;
}

export default function EvalsPage() {
  const { data: runs, isLoading } = useQuery({
    queryKey: ["evalRuns"],
    queryFn: api.listEvalRuns,
  });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const activeRunId = selectedRunId ?? runs?.[0]?.id ?? null;

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["evalRun", activeRunId],
    queryFn: () => api.getEvalRun(activeRunId as string),
    enabled: activeRunId !== null,
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-xl font-semibold">Evals</h1>
      <p className="mt-2 max-w-3xl text-ink/60">
        Persisted eval Runs over the far-25 corpus (spec §8). Only full-pipeline runs are stored —
        recall@k and MRR here come from those runs&apos; per-Case rows, not a separate
        retrieval-only trend.
      </p>

      <section className="mt-8">
        <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-ink/50">
          Latest baseline by suite
        </h2>
        <div className="mt-3 rounded-lg border border-line bg-card p-4">
          {isLoading || !runs ? (
            <p className="text-sm text-ink/40">Loading…</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-ink/40">No eval runs yet.</p>
          ) : (
            <EvalsChartSection runs={runs} />
          )}
        </div>
      </section>

      <section className="mt-10 overflow-x-auto">
        <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-ink/50">Runs</h2>
        <div className="mt-3">
          {isLoading ? (
            <p className="text-sm text-ink/40">Loading…</p>
          ) : !runs || runs.length === 0 ? (
            <p className="text-sm text-ink/40">No eval runs yet.</p>
          ) : (
            <EvalRunsTable
              runs={runs}
              selectedRunId={activeRunId}
              onSelect={(id) => setSelectedRunId(id)}
            />
          )}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-ink/50">
          Per-case drill-down
          {detail && (
            <span className="ml-2 normal-case tracking-normal text-ink/40">
              — {detail.run.suite} · <span className="font-mono">{detail.run.git_sha}</span>
            </span>
          )}
        </h2>
        <div className="mt-3 rounded-lg border border-line bg-card px-4">
          {detailLoading || !activeRunId ? (
            <p className="py-4 text-sm text-ink/40">
              {activeRunId ? "Loading…" : "Select a run above."}
            </p>
          ) : detail ? (
            <EvalCaseDrilldown results={detail.results} />
          ) : (
            <p className="py-4 text-sm text-ink/40">Run not found.</p>
          )}
        </div>
      </section>
    </main>
  );
}
