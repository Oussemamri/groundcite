"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";

const EMPTY_FIELDS = {
  slug: "",
  standard_code: "",
  title: "",
  organization: "",
  license_note: "",
  version: "",
  language: "en",
  source_url: "",
};

type Fields = typeof EMPTY_FIELDS;

function readNumber(result: Record<string, unknown> | null | undefined, key: string): number | null {
  const v = result?.[key];
  return typeof v === "number" ? v : null;
}

/**
 * Upload form + ingestion progress (spec §9, §10; AD-5). `POST /documents`
 * returns a job id immediately (202) -- ingestion (parse -> chunk -> embed
 * -> persist) runs as a BackgroundTask on the API and can take a while, so
 * progress is polled via `GET /jobs/{id}` (TanStack `refetchInterval` while
 * queued|running, AD-10) rather than held open on the upload request.
 */
export function UploadForm() {
  const queryClient = useQueryClient();
  const [fields, setFields] = useState<Fields>(EMPTY_FIELDS);
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1000 : false;
    },
  });

  const job = jobQuery.data ?? null;
  const isBusy = submitting || job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (job?.status === "done") {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  }, [job?.status, queryClient]);

  function updateField<K extends keyof Fields>(key: K, value: Fields[K]) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  function reset() {
    setFields(EMPTY_FIELDS);
    setFile(null);
    setJobId(null);
    setSubmitError(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setSubmitError("Choose a PDF first.");
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const created = await api.uploadDocument(file, {
        slug: fields.slug,
        standard_code: fields.standard_code,
        title: fields.title,
        organization: fields.organization,
        license_note: fields.license_note,
        version: fields.version || undefined,
        language: fields.language || undefined,
        source_url: fields.source_url || undefined,
      });
      setJobId(created.id);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? (err.problem.detail ?? err.problem.title) : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (job?.status === "done" || job?.status === "error") {
    const sectionsFound = readNumber(job.result, "sections_found");
    const chunksCreated = readNumber(job.result, "chunks_created");
    const attachedPct = readNumber(job.result, "attached_pct");
    return (
      <div
        className={
          "mt-4 rounded-lg border p-5 " +
          (job.status === "done" ? "border-grounded/30 bg-grounded/5" : "border-abstained/30 bg-abstained/5")
        }
      >
        {job.status === "done" ? (
          <>
            <h3 className="text-sm font-semibold text-text">Ingested</h3>
            <p className="mt-1 font-mono text-xs text-text/70">
              {sectionsFound ?? "?"} sections · {chunksCreated ?? "?"} chunks
              {attachedPct != null ? ` · ${(attachedPct * 100).toFixed(1)}% attached` : ""}
            </p>
          </>
        ) : (
          <>
            <h3 className="text-sm font-semibold text-text">Ingestion failed</h3>
            <p className="mt-1 text-sm text-text/60">{job.detail ?? "No detail returned."}</p>
          </>
        )}
        <button
          type="button"
          onClick={reset}
          className="mt-3 rounded border border-link px-3 py-1.5 text-xs text-link transition-colors hover:bg-link/10"
        >
          Upload another
        </button>
      </div>
    );
  }

  if (jobId && (job === null || job?.status === "queued" || job?.status === "running")) {
    return (
      <div className="mt-4 rounded-lg border border-border bg-surface p-5">
        <p role="status" className="flex items-center gap-2 text-sm text-text/70">
          <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-link" />
          {job?.status === "running" ? "Ingesting — parsing, chunking, embedding…" : "Queued for ingestion…"}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Slug" value={fields.slug} onChange={(v) => updateField("slug", v)} required />
        <Field
          label="Standard code"
          value={fields.standard_code}
          onChange={(v) => updateField("standard_code", v)}
          required
        />
        <Field label="Title" value={fields.title} onChange={(v) => updateField("title", v)} required className="sm:col-span-2" />
        <Field
          label="Organization"
          value={fields.organization}
          onChange={(v) => updateField("organization", v)}
          required
        />
        <Field label="Version" value={fields.version} onChange={(v) => updateField("version", v)} />
        <Field
          label="License note"
          value={fields.license_note}
          onChange={(v) => updateField("license_note", v)}
          required
          className="sm:col-span-2"
        />
        <Field label="Language" value={fields.language} onChange={(v) => updateField("language", v)} />
        <Field label="Source URL" value={fields.source_url} onChange={(v) => updateField("source_url", v)} />
      </div>

      <label className="text-xs text-text/60">
        PDF
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={isBusy}
          className="mt-1 block w-full text-sm text-text/70 file:mr-3 file:rounded file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-xs file:text-text disabled:opacity-50"
        />
      </label>

      {submitError && <p className="text-sm text-abstained">{submitError}</p>}

      <button
        type="submit"
        disabled={isBusy}
        className="self-start rounded border border-link px-4 py-2 text-sm text-link transition-colors hover:bg-link/10 disabled:cursor-not-allowed disabled:opacity-30"
      >
        {submitting ? "Uploading…" : "Upload"}
      </button>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  className?: string;
}) {
  return (
    <label className={"text-xs text-text/60 " + (className ?? "")}>
      {label}
      {required && <span className="text-abstained"> *</span>}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="mt-1 block w-full rounded border border-border bg-surface px-3 py-1.5 text-sm text-text placeholder:text-text/30 focus:border-link focus:outline-none focus:ring-1 focus:ring-link"
      />
    </label>
  );
}
