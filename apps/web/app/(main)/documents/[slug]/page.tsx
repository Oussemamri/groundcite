import { Suspense } from "react";
import { DocumentReaderClient } from "@/app/components/DocumentReaderClient";

/**
 * /documents/[slug] — reader: left clause tree, right content; `?chunk=`
 * deep-links highlight a chunk (spec §10).
 *
 * Note: the spec §4.1 sketch writes `documents/[id]`, but the document identity
 * used by the API and §10 is the `slug` (documents.slug is UNIQUE), so the route
 * param is `[slug]`.
 *
 * `DocumentReaderClient` reads `useSearchParams()` (the `chunk` deep-link) --
 * Next requires that behind a Suspense boundary so the route can still
 * prerender the shell instead of bailing the whole page to client rendering.
 */
export default async function DocumentReaderPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <main className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-6 py-10 lg:grid-cols-[280px_1fr]">
      <Suspense
        fallback={
          <>
            <aside aria-label="Clause tree" className="text-sm text-ink/40">
              Loading…
            </aside>
            <article className="text-sm text-ink/40">Loading…</article>
          </>
        }
      >
        <DocumentReaderClient slug={slug} />
      </Suspense>
    </main>
  );
}
