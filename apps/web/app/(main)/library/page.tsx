"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DocumentOut } from "@/lib/api";
import { UploadForm } from "@/app/components/UploadForm";

/**
 * One documents-table row (spec §10: org, code, version, chunks,
 * license_note). Chunk count comes from the same `?include=chunks` read the
 * reader page uses -- there's no lightweight count endpoint, and at v1's
 * corpus size (one document, 1,573 chunks) fetching it per row is cheap.
 * Would need a dedicated count field if the library grows past a handful
 * of documents.
 */
function DocumentRow({ doc }: { doc: DocumentOut }) {
  const { data } = useQuery({
    queryKey: ["document", doc.slug, "detail"],
    queryFn: () => api.getDocument(doc.slug, true),
  });
  const chunkCount = data?.chunks?.length;

  return (
    <tr className="border-b border-line last:border-0">
      <td className="py-3 pr-4">
        <Link href={`/documents/${encodeURIComponent(doc.slug)}`} className="text-accent hover:underline">
          {doc.title}
        </Link>
      </td>
      <td className="standard-code py-3 pr-4 text-xs text-ink/70">{doc.standard_code}</td>
      <td className="py-3 pr-4 text-ink/70">{doc.organization}</td>
      <td className="py-3 pr-4 font-mono text-xs text-ink/70">{doc.version ?? "—"}</td>
      <td className="py-3 pr-4 font-mono text-xs text-ink/70">{chunkCount ?? "…"}</td>
      <td className="py-3 text-xs text-ink/50">{doc.license_note}</td>
    </tr>
  );
}

export default function LibraryPage() {
  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-xl font-semibold">Library</h1>
      <p className="mt-2 text-ink/60">
        Ingested standards. Every answer on <span className="font-mono">/ask</span> cites back to a clause here.
      </p>

      <section className="mt-8 overflow-x-auto">
        {isLoading ? (
          <p className="text-sm text-ink/40">Loading…</p>
        ) : !documents || documents.length === 0 ? (
          <p className="text-sm text-ink/40">No documents ingested yet — upload one below.</p>
        ) : (
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-[0.14em] text-ink/40">
                <th className="pb-2 pr-4 font-medium">Title</th>
                <th className="pb-2 pr-4 font-medium">Code</th>
                <th className="pb-2 pr-4 font-medium">Organization</th>
                <th className="pb-2 pr-4 font-medium">Version</th>
                <th className="pb-2 pr-4 font-medium">Chunks</th>
                <th className="pb-2 font-medium">License</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <DocumentRow key={doc.slug} doc={doc} />
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="mt-10 max-w-xl">
        <h2 className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-ink/50">Upload a standard</h2>
        <UploadForm />
      </section>
    </main>
  );
}
