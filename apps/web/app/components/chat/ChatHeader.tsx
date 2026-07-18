"use client";

/** Sticky chat header (spec §2.2.1): hamburger toggles the sidebar, title +
 * corpus pill, a tagline that truncates and hides below 1360px alongside
 * the citations panel. */
export function ChatHeader({
  title,
  corpusCode,
  onToggleSidebar,
}: {
  title: string;
  corpusCode: string | null;
  onToggleSidebar: () => void;
}) {
  return (
    <header className="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-4 border-b border-chat-line bg-chat-header px-7 py-[13px] backdrop-blur">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          className="flex h-[30px] w-[30px] shrink-0 flex-col justify-center gap-[3px] rounded-md border border-chat-line px-[7px] transition-colors hover:bg-chat-ink/[0.06]"
        >
          <span className="block h-[1.5px] rounded-full bg-chat-ink" />
          <span className="block h-[1.5px] rounded-full bg-chat-ink" />
          <span className="block h-[1.5px] rounded-full bg-chat-ink" />
        </button>
        <h1 className="truncate font-serif text-sm font-semibold text-chat-ink">{title}</h1>
        {corpusCode && (
          <span className="shrink-0 rounded-full border border-chat-line-dim px-2.5 py-[3px] font-mono text-[10px] text-chat-ink/55">
            {corpusCode}
          </span>
        )}
      </div>
      <span className="hidden min-w-0 truncate font-mono text-[10px] text-chat-ink/35 min-[1360px]:block">
        every answer cites — or abstains
      </span>
    </header>
  );
}
