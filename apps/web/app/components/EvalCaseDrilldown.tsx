"use client";

import { useState } from "react";
import type { EvalResultDebug, EvalResultOut } from "@/lib/api";
import { clauseIdOf, citedClauseIsRelevant, expectedClauseIsHit } from "@/lib/clauseMatch";

function formatPct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;
}

function ClauseChip({ clause, hit }: { clause: string; hit: boolean }) {
  return (
    <span
      className={
        "rounded border px-1.5 py-0.5 font-mono text-[11px] " +
        (hit
          ? "border-grounded/40 bg-grounded/10 text-grounded"
          : "border-border bg-background text-text/60")
      }
    >
      {clauseIdOf(clause)}
    </span>
  );
}

/**
 * One case's expected-vs-cited detail (spec §10 "retrieved-vs-expected
 * clauses"; Week 5 AD-3). NOT the literal retrieved top-k -- that isn't
 * persisted for FULL runs (only recall@k NUMBERS + what got CITED are). This
 * renders exactly what IS stored: expected clauses, cited clauses with a
 * hit/miss highlight against them, the metric numbers, and abstention
 * correctness (must_abstain vs actual).
 */
function CaseRow({ result }: { result: EvalResultOut }) {
  const [open, setOpen] = useState(false);
  const debug = result.debug as unknown as EvalResultDebug;
  const citedClauses = debug.cited_clauses ?? [];
  const status = debug.status ?? "unknown";
  const abstained = result.abstained ?? status === "abstained";
  const mustAbstain = result.must_abstain ?? false;
  const correct = result.passed;

  return (
    <div className="border-b border-border last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 py-3 text-left hover:bg-surface/60"
      >
        <span
          aria-hidden
          className={
            "h-2 w-2 shrink-0 rounded-full " + (correct ? "bg-grounded" : "bg-abstained")
          }
          title={correct ? "abstention decision correct" : "abstention decision incorrect"}
        />
        <span className="flex-1 truncate text-sm text-text">
          {result.question ?? <span className="text-text/40">question unavailable</span>}
        </span>
        {mustAbstain && (
          <span className="shrink-0 rounded border border-abstained/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-abstained">
            must-abstain
          </span>
        )}
        <span className="shrink-0 font-mono text-xs text-text/60">
          {formatPct(result.recall_at_5)}
        </span>
        <span aria-hidden className="shrink-0 text-text/30">
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div className="pb-4 pl-5 text-sm">
          <p className="text-text/80">{result.question}</p>

          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">Recall@5</div>
              <div className="font-mono text-text">{formatPct(result.recall_at_5)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">Recall@10</div>
              <div className="font-mono text-text">{formatPct(result.recall_at_10)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">MRR</div>
              <div className="font-mono text-text">{formatPct(result.mrr)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">
                Citation precision
              </div>
              <div className="font-mono text-text">{formatPct(result.citation_precision)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">Top score</div>
              <div className="font-mono text-text">
                {debug.top_score === null || debug.top_score === undefined
                  ? "—"
                  : debug.top_score.toFixed(4)}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">Latency</div>
              <div className="font-mono text-text">
                {debug.latency_ms === null ? "—" : `${debug.latency_ms} ms`}
              </div>
            </div>
            <div className="col-span-2 sm:col-span-2">
              <div className="text-[10px] uppercase tracking-widest text-text/40">
                Abstention
              </div>
              <div className="text-text/80">
                must_abstain=<span className="font-mono">{String(mustAbstain)}</span>, actual=
                <span className="font-mono">{status}</span> —{" "}
                <span className={correct ? "text-grounded" : "text-abstained"}>
                  {correct ? "correct" : "incorrect"}
                </span>
              </div>
            </div>
          </div>

          {debug.error_message && (
            <p className="mt-3 text-xs text-abstained">Error: {debug.error_message}</p>
          )}

          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">
                Expected clauses
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {result.expected_clauses.length === 0 ? (
                  <span className="text-xs text-text/40">
                    none (must-abstain case has no expected clauses)
                  </span>
                ) : (
                  result.expected_clauses.map((c) => (
                    <ClauseChip key={c} clause={c} hit={expectedClauseIsHit(c, citedClauses)} />
                  ))
                )}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-text/40">
                Cited clauses{abstained ? " (none — abstained)" : ""}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {citedClauses.length === 0 ? (
                  <span className="text-xs text-text/40">—</span>
                ) : (
                  citedClauses.map((c, i) => (
                    <ClauseChip
                      key={`${c}-${i}`}
                      clause={c}
                      hit={citedClauseIsRelevant(c, result.expected_clauses)}
                    />
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function EvalCaseDrilldown({ results }: { results: EvalResultOut[] }) {
  if (results.length === 0) {
    return <p className="text-sm text-text/40">No per-case results for this run.</p>;
  }
  return (
    <div>
      {results.map((r) => (
        <CaseRow key={r.case_id} result={r} />
      ))}
    </div>
  );
}
