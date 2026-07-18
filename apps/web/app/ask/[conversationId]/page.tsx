import { ChatShell } from "@/app/components/chat/ChatShell";

/**
 * /ask/[conversationId] — load and continue a past conversation (spec
 * §2.2.1, Week 6). Same shell as the fresh-conversation /ask route
 * (DocumentReaderClient-style: one client component, parameterized).
 */
export default async function AskConversationPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = await params;
  return <ChatShell conversationId={conversationId} />;
}
