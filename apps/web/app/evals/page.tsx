/**
 * /evals — runs table + per-suite metric trend (recharts) + per-case drill-down
 * (retrieved vs. expected clauses). This page is the screenshot for the blog post
 * (spec §10). Empty shell; wired in Week 5.
 */
export default function EvalsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-xl font-semibold">Evals</h1>
      <p className="mt-2 text-text/60">
        Eval Runs, metric trends, and per-Case drill-downs live here (spec §8, §10).
      </p>
    </main>
  );
}
