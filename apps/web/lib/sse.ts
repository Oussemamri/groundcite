"use client";

/**
 * SSE event contract for the ask stream (spec §7) + the streaming reader and
 * React hook that consume it (Week 4 Phase 6/7).
 *
 * The event TYPES here mirror the core enums in
 * `core/groundcite/domain/results.py` (AskEventType / Stage) exactly — the
 * spec requires API and web to share one enum. If one side changes, change
 * both in the same PR (CLAUDE §6). The per-event DATA shapes mirror what
 * `AskService.ask()` actually puts on `AskEvent.data` (confirmed against
 * live SSE transcripts during Phase 3, not guessed).
 */

import { useCallback, useRef, useState } from "react";
import type { CitationOut } from "./api";

export type AskEventType = "stage" | "token" | "citations" | "final" | "error";

export type Stage = "retrieving" | "reranking" | "generating";

export interface StageEventData {
  stage: Stage;
}

export interface TokenEventData {
  token: string;
}

export interface CitationsEventData {
  citations: CitationOut[];
  answer_md: string;
}

export interface RetrievedPassage {
  chunk_id: string;
  clause_path: string;
  content: string;
  score: number;
}

export interface AnswerData {
  answer_md: string;
  citations: CitationOut[];
  insufficient: boolean;
  confidence: number | null;
}

export type AbstentionReason = "weak_retrieval" | "uncited";

export interface AbstentionData {
  reason: AbstentionReason;
  confidence: number | null;
  top_passages: RetrievedPassage[];
}

interface UsageData {
  prompt_tokens: number;
  completion_tokens: number;
}

export interface FinalGrounded {
  status: "grounded";
  answer: AnswerData;
  usage: UsageData;
  ask_id: string;
  latency_ms: number;
}

export interface FinalAbstained {
  status: "abstained";
  abstention: AbstentionData;
  usage: UsageData;
  ask_id: string;
  latency_ms: number;
}

export type FinalEventData = FinalGrounded | FinalAbstained;

export interface ErrorEventData {
  message: string;
}

export interface AskEvent {
  type: AskEventType;
  data: Record<string, unknown>;
}

/** Parse one SSE `event:`/`data:` frame into an {@link AskEvent}. */
export function parseSseFrame(frame: string): AskEvent | null {
  let type: AskEventType | null = null;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim() as AskEventType;
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (type === null) return null;
  const raw = dataLines.join("\n");
  return { type, data: raw ? (JSON.parse(raw) as Record<string, unknown>) : {} };
}

/**
 * Consume a `POST /api/v1/asks` SSE response as an async stream of typed
 * events. sse-starlette (the server) uses `\r\n` line endings and separates
 * frames with a blank line (`\r\n\r\n`) -- also sends `: ping - <ts>`
 * comment lines during long CPU-bound stages (reranking) to keep the
 * connection alive; those are skipped, not surfaced as events.
 */
export async function* readAskStream(response: Response): AsyncGenerator<AskEvent> {
  if (!response.body) throw new Error("response has no body to stream");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // A frame ends at a blank line; sse-starlette's line ending is \r\n.
      let sepIndex: number;
      while ((sepIndex = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const match = /\r?\n\r?\n/.exec(buffer.slice(sepIndex))!;
        const frame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + match[0].length);
        if (frame.trim().startsWith(":")) continue; // ping/keep-alive comment
        const event = parseSseFrame(frame);
        if (event) yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export type AskStreamStatus = "idle" | "streaming" | "grounded" | "abstained" | "error";

export interface AskStreamState {
  status: AskStreamStatus;
  stage: Stage | null;
  answerMd: string;
  citations: CitationOut[];
  final: FinalEventData | null;
  errorMessage: string | null;
}

const initialState: AskStreamState = {
  status: "idle",
  stage: null,
  answerMd: "",
  citations: [],
  final: null,
  errorMessage: null,
};

/**
 * Drives `POST /api/v1/asks` and exposes live state as tokens/citations/
 * the terminal event arrive. One `start()` call per Ask; calling it again
 * begins a fresh stream and resets state.
 */
export function useAskStream() {
  const [state, setState] = useState<AskStreamState>(initialState);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback((question: string, documentSlugs?: string[]) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ ...initialState, status: "streaming" });

    void (async () => {
      try {
        const res = await fetch("/api/v1/asks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, document_slugs: documentSlugs ?? null }),
          signal: controller.signal,
        });
        if (!res.ok) {
          setState((s) => ({ ...s, status: "error", errorMessage: `HTTP ${res.status}` }));
          return;
        }
        for await (const event of readAskStream(res)) {
          if (event.type === "stage") {
            const data = event.data as unknown as StageEventData;
            setState((s) => ({ ...s, stage: data.stage }));
          } else if (event.type === "token") {
            const data = event.data as unknown as TokenEventData;
            setState((s) => ({ ...s, answerMd: s.answerMd + data.token }));
          } else if (event.type === "citations") {
            const data = event.data as unknown as CitationsEventData;
            setState((s) => ({ ...s, citations: data.citations, answerMd: data.answer_md }));
          } else if (event.type === "final") {
            const data = event.data as unknown as FinalEventData;
            setState((s) => ({
              ...s,
              status: data.status,
              final: data,
              citations: data.status === "grounded" ? data.answer.citations : s.citations,
              answerMd: data.status === "grounded" ? data.answer.answer_md : s.answerMd,
            }));
          } else if (event.type === "error") {
            const data = event.data as unknown as ErrorEventData;
            setState((s) => ({ ...s, status: "error", errorMessage: data.message }));
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return; // a fresh start() superseded this one
        setState((s) => ({
          ...s,
          status: "error",
          errorMessage: err instanceof Error ? err.message : String(err),
        }));
      }
    })();
  }, []);

  return { ...state, start };
}
