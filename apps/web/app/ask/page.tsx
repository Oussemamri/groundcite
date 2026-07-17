"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AbstentionCard } from "@/app/components/AbstentionCard";
import { CitationCard } from "@/app/components/CitationCard";
import { PipelineStatus } from "@/app/components/PipelineStatus";
import { StatusChip } from "@/app/components/StatusChip";
import { api } from "@/lib/api";
import { renderAnswerMd } from "@/lib/markdown";
import { useAskStream } from "@/lib/sse";

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const stream = useAskStream();

  // CitationOut carries no document identifier (spec §7 contract) -- with a
  // single-document library this is unambiguous, so a citation click can
  // still open the reader at the right chunk. Once the library holds more
  // than one document, this needs a real `document_slug` on Citation to stay
  // correct instead of guessing; noted as a residual, not built speculatively.
  const { data: documents } = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });
  const documentSlug = documents?.length === 1 ? documents[0]?.slug : undefined;

  const isStreaming = stream.status === "streaming";
  const isTerminal = stream.status === "grounded" || stream.status === "abstained";

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || isStreaming) return;
    stream.start(q);
  }

  const passages =
    stream.final?.status === "abstained"
      ? stream.final.abstention.top_passages
      : stream.citations.map((c) => ({
          chunk_id: c.chunk_id,
          clause_path: c.clause_path ?? "",
          content: c.claim ?? "",
          score: c.score,
        }));

  const groundedConfidence = stream.final?.status === "grounded" ? stream.final.answer.confidence : null;

  return (
    <main className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-6 py-10 lg:grid-cols-[1fr_360px]">
      <section aria-label="Ask">
        <h1 className="text-xl font-semibold">Ask</h1>
        <p className="mt-2 text-text/60">
          Ask a question about an ingested standard. Every answer carries verifiable clause
          citations — or the system abstains.
        </p>

        <form onSubmit={onSubmit} className="mt-6 flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What does §25.1309(b) require for catastrophic failure conditions?"
            disabled={isStreaming}
            className="flex-1 rounded border border-border bg-surface px-4 py-2.5 text-sm text-text placeholder:text-text/30 focus:border-link focus:outline-none focus:ring-1 focus:ring-link disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isStreaming || !question.trim()}
            className="rounded border border-link px-4 py-2.5 text-sm text-link transition-colors hover:bg-link/10 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {isStreaming ? "Asking…" : "Ask"}
          </button>
        </form>

        {stream.status !== "idle" && (
          <div className="mt-6">
            <PipelineStatus
              currentStage={stream.stage}
              done={isTerminal || stream.status === "error"}
            />

            {stream.status === "error" && (
              <div className="mt-4 rounded-lg border border-abstained/30 bg-abstained/5 p-5">
                <h2 className="text-base font-semibold text-text">Something went wrong</h2>
                <p className="mt-1 text-sm text-text/60">{stream.errorMessage}</p>
              </div>
            )}

            {stream.status === "abstained" && stream.final?.status === "abstained" && (
              <div className="mt-4">
                <AbstentionCard reason={stream.final.abstention.reason} />
              </div>
            )}

            {(isStreaming || stream.status === "grounded") && stream.answerMd && (
              <div className="mt-4 rounded-lg border border-border bg-surface p-5">
                {stream.status === "grounded" && (
                  <div className="mb-3">
                    <StatusChip status="grounded" confidence={groundedConfidence} />
                  </div>
                )}
                <div className="text-sm leading-relaxed text-text">
                  {renderAnswerMd(stream.answerMd)}
                  {isStreaming && (
                    <span
                      aria-hidden
                      className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-link align-text-bottom"
                    />
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <aside aria-label="Citations" className="rounded-lg border border-border bg-surface p-4">
        <h2 className="text-xs font-medium uppercase tracking-widest text-text/50">
          {stream.status === "abstained" ? "Closest passages" : "Citations"}
        </h2>
        {passages.length === 0 ? (
          <p className="mt-3 text-sm text-text/40">
            {stream.status === "idle" ? "Citations will appear here." : "—"}
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {passages.map((p, i) => (
              <CitationCard
                key={`${p.chunk_id}-${i}`}
                clausePath={p.clause_path}
                chunkId={p.chunk_id}
                score={p.score}
                snippet={p.content}
                documentSlug={documentSlug}
              />
            ))}
          </div>
        )}
      </aside>
    </main>
  );
}
