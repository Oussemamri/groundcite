/**
 * /ask — question input + streaming answer, with a citation side-panel and a
 * GROUNDED/ABSTAINED status chip (spec §10). P5 is an empty shell; the streaming
 * SSE flow (lib/sse.ts) and citation cards land in Week 4.
 */
export default function AskPage() {
  return (
    <main className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-6 py-10 lg:grid-cols-[1fr_360px]">
      <section aria-label="Ask">
        <h1 className="text-xl font-semibold">Ask</h1>
        <p className="mt-2 text-text/60">
          Ask a question about an ingested standard. Every answer carries verifiable clause
          citations — or the system abstains.
        </p>
        {/* Question input + streamed answer render here in Week 4. */}
      </section>

      <aside
        aria-label="Citations"
        className="rounded-lg border border-border bg-surface p-4 text-text/60"
      >
        {/* Citation cards: clause_path (mono), snippet, score (spec §10). */}
        Citations will appear here.
      </aside>
    </main>
  );
}
