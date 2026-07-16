import { Fragment, type ReactNode } from "react";

/**
 * Minimal, safe renderer for the generator's `answer_md` (spec §7 contract).
 * Handles only what real generation output actually uses (confirmed against
 * live transcripts, Phase 3): paragraphs and `**bold**`. No dependency, no
 * `dangerouslySetInnerHTML` -- plain text always renders as plain text,
 * regardless of content, since this ultimately comes from an LLM.
 */
export function renderAnswerMd(text: string): ReactNode[] {
  return text
    .split(/\n{2,}/)
    .filter((p) => p.trim())
    .map((paragraph, pIdx) => (
      <p key={pIdx} className={pIdx > 0 ? "mt-3" : undefined}>
        {renderInline(paragraph)}
      </p>
    ));
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
