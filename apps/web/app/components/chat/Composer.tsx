"use client";

/** Fixed-bottom composer (spec §2.2.1). */
export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  tauRetrieval,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  tauRetrieval: number | null;
}) {
  return (
    <div className="shrink-0 border-t border-chat-line bg-chat-panel px-6 pb-4 pt-3.5">
      <div className="mx-auto max-w-[768px]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
          className="flex gap-2 rounded-[10px] border border-chat-line-user bg-chat-composer py-1.5 pl-4 pr-1.5"
        >
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Ask about an ingested standard…"
            disabled={disabled}
            className="flex-1 border-none bg-transparent py-2 font-serif text-sm text-chat-ink outline-none placeholder:text-chat-ink/30 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="shrink-0 rounded-[7px] bg-chat-accent px-[18px] py-[9px] font-serif text-[13px] font-semibold text-chat-bg transition-colors hover:bg-chat-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {disabled ? "Asking…" : "Send"}
          </button>
        </form>
        <div className="mt-2 text-center font-mono text-[10px] text-chat-ink/30">
          answers carry verifiable clause citations — or the system abstains
          {tauRetrieval !== null && ` · τ_retrieval ${tauRetrieval.toFixed(2)}`}
        </div>
      </div>
    </div>
  );
}
