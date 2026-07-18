import { ChatShell } from "@/app/components/chat/ChatShell";

/**
 * /ask — a fresh conversation (spec §2.2.1, Week 6). No site-wide <Nav />
 * here (see app/(main)/layout.tsx) -- the chat sidebar's wordmark row is
 * this page's own nav.
 */
export default function AskPage() {
  return <ChatShell conversationId={null} />;
}
