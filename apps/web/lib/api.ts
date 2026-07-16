/**
 * Typed API client (spec §9; Week 4 Phase 6).
 *
 * Thin fetch wrappers over `/api/v1/*` (proxied same-origin via next.config.mjs
 * rewrites, AD-3 -- no base URL, no CORS). Types mirror `apps/api/app/models.py`
 * field-for-field; change both in the same PR (CLAUDE §6).
 */

export interface DocumentOut {
  slug: string;
  standard_code: string;
  title: string;
  organization: string;
  version: string | null;
  language: string;
  source_url: string | null;
  license_note: string;
  ingested_at: string | null;
}

export interface SectionOut {
  id: string;
  parent_id: string | null;
  clause_id: string;
  title: string | null;
  level: number;
  ordinal: number;
}

export interface ChunkOut {
  id: string;
  document_id: string;
  section_id: string;
  clause_path: string;
  content: string;
  token_count: number;
  page_start: number | null;
  page_end: number | null;
}

export interface DocumentDetailOut {
  document: DocumentOut;
  sections: SectionOut[];
  chunks: ChunkOut[] | null;
}

export interface CitationOut {
  chunk_id: string;
  rank: number;
  score: number;
  claim: string | null;
  clause_path: string | null;
}

export interface AskOut {
  id: string;
  question: string;
  status: string;
  answer_md: string | null;
  confidence: number | null;
  latency_ms: number | null;
  cost_usd: string | null;
  pipeline_debug: Record<string, unknown>;
  created_at: string | null;
  citations: CitationOut[];
}

export interface EvalRunOut {
  id: string;
  git_sha: string;
  config: Record<string, unknown>;
}

export interface EvalResultOut {
  run_id: string;
  case_id: string;
  recall_at_5: number | null;
  recall_at_10: number | null;
  mrr: number | null;
  citation_precision: number | null;
  faithfulness: number | null;
  abstained: boolean | null;
  passed: boolean;
  debug: Record<string, unknown>;
}

export interface EvalRunDetailOut {
  run: EvalRunOut;
  results: EvalResultOut[];
}

export interface JobOut {
  id: string;
  kind: "ingest" | "eval_run";
  status: "queued" | "running" | "done" | "error";
  detail: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
}

/** RFC-7807 problem+json (AD-6) -- every non-2xx response has this shape. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string | null;
  instance: string;
}

export class ApiError extends Error {
  constructor(
    public readonly problem: Problem,
    public readonly status: number,
  ) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies (uploadDocument) must NOT get a Content-Type header set
  // here -- fetch computes `multipart/form-data; boundary=...` itself from
  // the FormData instance, and overriding it with "application/json" would
  // silently break the upload (the server would fail to parse the body).
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(path, {
    ...init,
    headers: isFormData ? init?.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const problem = (await res.json()) as Problem;
    throw new ApiError(problem, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDocuments: () => request<DocumentOut[]>("/api/v1/documents"),

  getDocument: (slug: string, includeChunks = false) =>
    request<DocumentDetailOut>(
      `/api/v1/documents/${encodeURIComponent(slug)}${includeChunks ? "?include=chunks" : ""}`,
    ),

  getChunk: (chunkId: string) => request<ChunkOut>(`/api/v1/chunks/${encodeURIComponent(chunkId)}`),

  getAsk: (askId: string) => request<AskOut>(`/api/v1/asks/${encodeURIComponent(askId)}`),

  listEvalRuns: () => request<EvalRunOut[]>("/api/v1/eval/runs"),

  getEvalRun: (runId: string) => request<EvalRunDetailOut>(`/api/v1/eval/runs/${encodeURIComponent(runId)}`),

  triggerEvalRun: (suite: string, full: boolean) =>
    request<JobOut>("/api/v1/eval/runs", {
      method: "POST",
      body: JSON.stringify({ suite, full }),
    }),

  getJob: (jobId: string) => request<JobOut>(`/api/v1/jobs/${encodeURIComponent(jobId)}`),

  uploadDocument: (file: File, meta: {
    slug: string;
    standard_code: string;
    title: string;
    organization: string;
    license_note: string;
    version?: string;
    language?: string;
    source_url?: string;
  }) => {
    const form = new FormData();
    form.set("file", file);
    for (const [k, v] of Object.entries(meta)) {
      if (v !== undefined) form.set(k, v);
    }
    return request<JobOut>("/api/v1/documents", { method: "POST", body: form });
  },
};
