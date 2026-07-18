"use client";

import { useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ClauseTree } from "@/app/components/ClauseTree";

function pageRange(start: number | null, end: number | null): string | null {
  if (start == null) return null;
  return end != null && end !== start ? `p. ${start}–${end}` : `p. ${start}`;
}

/**
 * The reader (spec §10): left clause tree, right ordered chunk content.
 * `?chunk=<id>` (set by CitationCard links from /ask) scrolls to and
 * highlights that chunk -- this is where the citation-resolution loop
 * closes. A client component so it can read the `chunk` query param and
 * drive TanStack Query; the page itself stays a server component that only
 * awaits the `slug` route param.
 */
export function DocumentReaderClient({ slug }: { slug: string }) {
  const searchParams = useSearchParams();
  const chunkId = searchParams.get("chunk");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["document", slug, "detail"],
    queryFn: () => api.getDocument(slug, true),
  });

  // `data?.chunks ?? []` would produce a fresh array every render, defeating
  // useMemo below -- memoize it so the empty-array fallback is stable too.
  const chunks = useMemo(() => data?.chunks ?? [], [data]);

  const activeSectionId = useMemo(() => {
    if (!chunkId) return null;
    return chunks.find((c) => c.id === chunkId)?.section_id ?? null;
  }, [chunkId, chunks]);

  const highlightRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [chunkId, data]);

  function scrollToSection(sectionId: string) {
    const el = document.querySelector<HTMLElement>(`[data-section-id="${sectionId}"]`);
    el?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  if (isLoading) {
    return (
      <>
        <aside aria-label="Clause tree" className="text-sm text-ink/40">
          Loading…
        </aside>
        <article className="text-sm text-ink/40">Loading…</article>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <aside aria-label="Clause tree" />
        <article>
          <h1 className="font-mono text-lg">{slug}</h1>
          <p className="mt-3 text-sm text-abstained">
            {error instanceof Error ? error.message : `No document found for "${slug}".`}
          </p>
        </article>
      </>
    );
  }

  // Destructured as `doc`, not `document` -- the latter would shadow the
  // global DOM `document` that `scrollToSection` above relies on.
  const { document: doc, sections } = data;

  return (
    <>
      <aside
        aria-label="Clause tree"
        className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-2"
      >
        <ClauseTree sections={sections} activeSectionId={activeSectionId} onSelect={scrollToSection} />
      </aside>

      <article>
        <header className="border-b border-line pb-4">
          <h1 className="text-lg font-semibold text-ink">{doc.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink/50">
            <span className="standard-code text-ink/70">{doc.standard_code}</span>
            <span>{doc.organization}</span>
            {doc.version && <span className="font-mono">{doc.version}</span>}
            <span>{doc.license_note}</span>
          </p>
        </header>

        <div className="mt-6 flex flex-col gap-3">
          {chunks.length === 0 ? (
            <p className="text-sm text-ink/40">This document has no chunks yet.</p>
          ) : (
            chunks.map((chunk) => {
              const isActive = chunk.id === chunkId;
              const pages = pageRange(chunk.page_start, chunk.page_end);
              return (
                <div
                  key={chunk.id}
                  ref={isActive ? highlightRef : undefined}
                  data-section-id={chunk.section_id}
                  className={
                    "scroll-mt-24 rounded border p-4 text-sm transition-colors " +
                    (isActive ? "border-accent bg-accent/5" : "border-line bg-card")
                  }
                >
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs text-ink/50">
                    <span className="font-mono">{chunk.clause_path}</span>
                    {pages && <span className="font-mono">{pages}</span>}
                  </div>
                  <p className="whitespace-pre-wrap leading-relaxed text-ink/90">{chunk.content}</p>
                </div>
              );
            })
          )}
        </div>
      </article>
    </>
  );
}
