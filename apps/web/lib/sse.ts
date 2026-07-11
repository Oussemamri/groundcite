/**
 * SSE event contract for the ask stream (spec §7).
 *
 * These types MUST mirror the core enums in
 * `core/groundcite/domain/results.py` (AskEventType / Stage) exactly — the spec
 * requires API and web to share one enum. If one side changes, change both in
 * the same PR (CLAUDE §6).
 */

export type AskEventType = "stage" | "token" | "citations" | "final" | "error";

export type Stage = "retrieving" | "reranking" | "generating";

export interface AskEvent {
  type: AskEventType;
  data: Record<string, unknown>;
}

/**
 * Parse one SSE `event:`/`data:` frame into an {@link AskEvent}.
 * Full streaming reader (fetch + ReadableStream) lands with `/ask` in Week 4.
 */
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
