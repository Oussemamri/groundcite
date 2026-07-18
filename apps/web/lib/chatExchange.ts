/**
 * One normalized chat turn (Week 6) -- the shape `ExchangeCard` renders,
 * whatever it came from: a live `useAskStream` state (still streaming or
 * just finished) or a past turn loaded via `GET /conversations/{id}`
 * (`AskOut`). Two very different wire shapes (nested SSE `final.answer`/
 * `final.abstention` vs. flat `AskOut` fields) collapse into one here so
 * `ExchangeCard` only ever needs to know one shape.
 */

import type { AskOut, CitationOut } from "./api";
import type { AbstentionReason, AskStreamState, RetrievedPassage } from "./sse";

export interface Exchange {
  question: string;
  /** null once the turn is done (loaded from history, or a live stream that
   * reached a terminal state) -- ExchangeCard treats null as "done". */
  stage: AskStreamState["stage"];
  streaming: boolean;
  status: "grounded" | "abstained" | "error" | null;
  answerMd: string;
  confidence: number | null;
  citations: CitationOut[];
  abstentionReason: AbstentionReason | null;
  /** Only ever populated for a LIVE abstained turn -- top_passages is an
   * SSE-only payload, never persisted to the asks table (a real, accepted
   * gap: a reloaded past conversation cannot show a historical abstained
   * turn's closest passages, only that it abstained and why). */
  topPassages: RetrievedPassage[];
  errorMessage: string | null;
  askId: string | null;
  latencyMs: number | null;
}

/** A live `useAskStream()` state, tagged with the question that started it. */
export function liveStateToExchange(question: string, state: AskStreamState): Exchange {
  const streaming = state.status === "streaming";
  const status =
    state.status === "grounded" || state.status === "abstained" || state.status === "error"
      ? state.status
      : null;
  const final = state.final;
  return {
    question,
    stage: state.stage,
    streaming,
    status,
    answerMd: state.answerMd,
    confidence: final?.status === "grounded" ? final.answer.confidence : null,
    citations: state.citations,
    abstentionReason: final?.status === "abstained" ? final.abstention.reason : null,
    topPassages: final?.status === "abstained" ? final.abstention.top_passages : [],
    errorMessage: state.errorMessage,
    askId: final?.ask_id ?? null,
    latencyMs: final?.latency_ms ?? null,
  };
}

/** A past turn loaded via `GET /conversations/{id}` (spec §9). */
export function askToExchange(ask: AskOut): Exchange {
  const status = ask.status === "grounded" || ask.status === "abstained" ? ask.status : "error";
  // PipelineStatus lights every stage up to and including `stage` -- a
  // replayed Ask has no persisted per-stage history, but its terminal
  // status alone tells us how far it truthfully got: grounded reached
  // generating; abstained never reaches generating at all (Gate A blocks
  // first, spec §7). An unknown/error replay stays null (honestly "unknown
  // how far it got") rather than guessing.
  const stage = status === "grounded" ? "generating" : status === "abstained" ? "reranking" : null;
  return {
    question: ask.question,
    stage,
    streaming: false,
    status,
    answerMd: ask.answer_md ?? "",
    confidence: ask.confidence,
    citations: ask.citations,
    // AskOut carries no abstention reason field -- see module docstring on
    // the reason/top_passages gap for a replayed abstained turn.
    abstentionReason: null,
    topPassages: [],
    errorMessage: null,
    askId: ask.id,
    latencyMs: ask.latency_ms,
  };
}
