"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAskStream } from "@/lib/sse";
import { askToExchange, liveStateToExchange, type Exchange } from "@/lib/chatExchange";
import { ChatHeader } from "./ChatHeader";
import { CitationsPanel } from "./CitationsPanel";
import { Composer } from "./Composer";
import { ExchangeCard } from "./ExchangeCard";
import { Sidebar } from "./Sidebar";

const SIDEBAR_BREAKPOINT = 1100;

/**
 * The `/ask` chat page (spec §2.2, Week 6) -- one component shared by
 * `/ask` (fresh conversation, `conversationId` null) and
 * `/ask/[conversationId]` (load and continue a past one), mirroring the
 * existing `DocumentReaderClient` pattern (one component, parameterized by
 * an optional id, used by both routes).
 *
 * Deliberately does NOT rewrite `useAskStream` (`lib/sse.ts`) to natively
 * hold an array -- that hook stays single-exchange and well-tested.
 * Instead: `completedExchanges` holds every turn that's done (either
 * archived from a finished live stream, or loaded from history);
 * `useAskStream()` drives whichever ONE exchange is currently in flight.
 */
export function ChatShell({ conversationId: initialConversationId }: { conversationId: string | null }) {
  const queryClient = useQueryClient();
  const stream = useAskStream();
  const threadRef = useRef<HTMLDivElement>(null);

  const [input, setInput] = useState("");
  const [completedExchanges, setCompletedExchanges] = useState<Exchange[]>([]);
  const [liveQuestion, setLiveQuestion] = useState<string | null>(null);
  // The conversation this shell is actually posting to -- starts as the
  // route param, but a fresh /ask session only learns its real id once the
  // FIRST message's FINAL event arrives (the server auto-creates it). Kept
  // as internal state (not re-derived from the prop) so every message after
  // the first still targets the SAME conversation without a real navigation.
  const [activeConversationId, setActiveConversationId] = useState(initialConversationId);
  const [seededFromHistory, setSeededFromHistory] = useState(initialConversationId === null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    setSidebarOpen(window.innerWidth >= SIDEBAR_BREAKPOINT);
  }, []);

  const { data: conversationDetail } = useQuery({
    queryKey: ["conversation", initialConversationId],
    queryFn: () => api.getConversation(initialConversationId as string),
    enabled: initialConversationId !== null,
  });

  useEffect(() => {
    if (conversationDetail && !seededFromHistory) {
      setCompletedExchanges(conversationDetail.asks.map(askToExchange));
      setSeededFromHistory(true);
    }
  }, [conversationDetail, seededFromHistory]);

  // A fresh conversation created by the first message: sync the URL bar
  // silently (raw History API, not next/navigation's router -- a real
  // App Router navigation between /ask and /ask/[id] would unmount and
  // remount this whole component, losing the in-progress thread). A real
  // page refresh afterward correctly lands on /ask/[id]'s own server render.
  useEffect(() => {
    if (activeConversationId === null && stream.final?.conversation_id) {
      const id = stream.final.conversation_id;
      setActiveConversationId(id);
      window.history.replaceState(null, "", `/ask/${id}`);
    }
    if (stream.final) {
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  }, [stream.final, activeConversationId, queryClient]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [completedExchanges, stream.answerMd, stream.status]);

  const { data: documents } = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });
  // Single-document assumption, same as the reader's citation resolution
  // (GitHub issue #3) -- not a new gap introduced here.
  const soleDoc = documents?.length === 1 ? documents[0] : undefined;
  const documentSlug = soleDoc?.slug;
  const { data: docDetail } = useQuery({
    queryKey: ["document", documentSlug, "detail"],
    queryFn: () => api.getDocument(documentSlug as string, true),
    enabled: documentSlug !== undefined,
  });
  const { data: health } = useQuery({ queryKey: ["healthz"], queryFn: api.healthz });
  const tauRetrieval = health?.config.tau_retrieval ?? null;

  function handleSubmit() {
    const question = input.trim();
    if (!question || stream.status === "streaming") return;

    if (liveQuestion !== null && stream.status !== "idle") {
      setCompletedExchanges((prev) => [...prev, liveStateToExchange(liveQuestion, stream)]);
    }
    setLiveQuestion(question);
    setInput("");
    stream.start(question, activeConversationId ?? undefined);
  }

  const liveExchange: Exchange | null =
    liveQuestion !== null && stream.status !== "idle"
      ? liveStateToExchange(liveQuestion, stream)
      : null;
  const allExchanges = liveExchange ? [...completedExchanges, liveExchange] : completedExchanges;
  const latest = allExchanges[allExchanges.length - 1];

  const activeConversation = (conversationDetail?.conversation.id === activeConversationId
    ? conversationDetail.conversation.title
    : undefined) ?? (allExchanges.length > 0 ? allExchanges[0]?.question : undefined);

  return (
    <div className="flex h-dvh overflow-hidden bg-paper text-ink">
      <Sidebar
        open={sidebarOpen}
        activeConversationId={activeConversationId}
        corpusCode={soleDoc?.standard_code ?? null}
        chunkCount={docDetail?.chunks?.length ?? null}
        tauRetrieval={tauRetrieval}
      />
      {/* Backdrop for the <1100px overlay sidebar (see Sidebar.tsx) -- a
          no-op at >=1100px, where the sidebar pushes in-flow instead. */}
      {sidebarOpen && (
        <div
          aria-hidden
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-20 hidden bg-black/30 max-[1099px]:block"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <ChatHeader
          title={activeConversation ?? "New ask"}
          corpusCode={soleDoc?.standard_code ?? null}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />

        <div ref={threadRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-[768px] flex-col gap-7 px-6 py-8">
            {allExchanges.length === 0 && (
              <p className="text-sm text-ink/40">
                Ask a question about an ingested standard — every answer carries verifiable
                clause citations, or the system abstains.
              </p>
            )}
            {allExchanges.map((exchange, i) => (
              <ExchangeCard
                key={exchange.askId ?? `live-${i}`}
                exchange={exchange}
                documentSlug={documentSlug}
              />
            ))}
          </div>
        </div>

        <Composer
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          disabled={stream.status === "streaming"}
          tauRetrieval={tauRetrieval}
        />
      </div>

      <CitationsPanel latest={latest} documentSlug={documentSlug} tauRetrieval={tauRetrieval} />
    </div>
  );
}
