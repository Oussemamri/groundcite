/**
 * /library — documents table (org, code, version, chunks, license_note) + upload
 * with ingestion progress (spec §10). Empty shell; wired in Week 4.
 */
export default function LibraryPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-xl font-semibold">Library</h1>
      <p className="mt-2 text-text/60">Ingested standards and upload live here (spec §10).</p>
    </main>
  );
}
