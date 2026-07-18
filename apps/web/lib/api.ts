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

/** A conversation summary (Week 6, spec §9 GET /conversations). Groups
 * already-independent Asks -- turn_count/latest_status are read-only,
 * derived at read time (never re-computed generation state). */
export interface ConversationOut {
  id: string;
  title: string;
  created_at: string | null;
  turn_count: number | null;
  latest_status: string | null;
}

/** One conversation's full turn history (spec §9 GET /conversations/{id})
 * -- each turn the same shape GET /asks/{id} already returns. */
export interface ConversationDetailOut {
  conversation: ConversationOut;
  asks: AskOut[];
}

export interface EvalRunOut {
  id: string;
  git_sha: string;
  config: Record<string, unknown>;
  started_at: string | null;
  suite: string | null;
}

export interface EvalResultOut {
  run_id: string;
  case_id: string;
  // Case metadata (Week 5 AD-2), joined from eval_cases; null when the case
  // id is unknown (never fabricated -- should not happen for a real run).
  question: string | null;
  expected_clauses: string[];
  must_abstain: boolean | null;
  language: string | null;
  recall_at_5: number | null;
  recall_at_10: number | null;
  mrr: number | null;
  citation_precision: number | null;
  faithfulness: number | null;
  abstained: boolean | null;
  passed: boolean;
  debug: Record<string, unknown>;
}

/** Shape of `EvalResultOut.debug` for a FULL-pipeline run (services/eval.py
 * run_full, not mirrored 1:1 as its own response field since it's already a
 * plain jsonb column -- narrows the `Record<string, unknown>` at read sites
 * instead of adding parallel typed fields for data already on the wire). */
export interface EvalResultDebug {
  ask_id: string | null;
  status: string;
  top_score: number | null;
  latency_ms: number | null;
  cited_clauses: string[];
  error_message: string | null;
}

/** Per-run headline metrics (Week 5 AD-2/AD-4), computed by the API from the
 * already-persisted per-case rows -- never a re-run (rule 4). */
export interface EvalRunAggregatesOut {
  scored_cases: number;
  mean_recall_at_5: number | null;
  mean_recall_at_10: number | null;
  mean_mrr: number | null;
  mean_citation_precision: number | null;
  abstention_accuracy: number | null;
}

export interface EvalRunDetailOut {
  run: EvalRunOut;
  results: EvalResultOut[];
  aggregates: EvalRunAggregatesOut;
}

export interface JobOut {
  id: string;
  kind: "ingest" | "eval_run";
  status: "queued" | "running" | "done" | "error";
  detail: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
}

/** GET /healthz (spec §9/§12). `config` carries the live tau_retrieval /
 * groq_model / llm_provider / reranker_enabled -- Week 6's chat composer
 * and run-detail panel show the real running threshold, not a guess. */
export interface HealthOut {
  status: string;
  checks: Record<string, string>;
  config: {
    tau_retrieval?: number;
    groq_model?: string;
    llm_provider?: string;
    reranker_enabled?: boolean;
  };
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
  healthz: () => request<HealthOut>("/healthz"),

  listDocuments: () => request<DocumentOut[]>("/api/v1/documents"),

  getDocument: (slug: string, includeChunks = false) =>
    request<DocumentDetailOut>(
      `/api/v1/documents/${encodeURIComponent(slug)}${includeChunks ? "?include=chunks" : ""}`,
    ),

  getChunk: (chunkId: string) => request<ChunkOut>(`/api/v1/chunks/${encodeURIComponent(chunkId)}`),

  getAsk: (askId: string) => request<AskOut>(`/api/v1/asks/${encodeURIComponent(askId)}`),

  listConversations: () => request<ConversationOut[]>("/api/v1/conversations"),

  getConversation: (conversationId: string) =>
    request<ConversationDetailOut>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}`,
    ),

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
