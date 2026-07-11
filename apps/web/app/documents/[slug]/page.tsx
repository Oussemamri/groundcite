/**
 * /documents/[slug] — reader: left clause tree, right content; `?chunk=`
 * deep-links highlight a chunk (spec §10). Empty shell; wired in Week 4.
 *
 * Note: the spec §4.1 sketch writes `documents/[id]`, but the document identity
 * used by the API and §10 is the `slug` (documents.slug is UNIQUE), so the route
 * param is `[slug]`.
 */
export default async function DocumentReaderPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <main className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-6 py-10 lg:grid-cols-[280px_1fr]">
      <aside aria-label="Clause tree" className="text-text/60">
        {/* Clause tree (Section hierarchy) renders here. */}
        Clause tree
      </aside>
      <article>
        <h1 className="font-mono text-lg">{slug}</h1>
        <p className="mt-2 text-text/60">Document content renders here (spec §10).</p>
      </article>
    </main>
  );
}
