"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/ask", label: "Ask" },
  { href: "/library", label: "Library" },
  { href: "/evals", label: "Evals" },
];

/** Shared top nav for every page except `/ask` (spec §2.2 — `/ask`'s chat
 * sidebar carries its own wordmark row instead). Warm paper theme: sticky
 * translucent header, mono wordmark with the grounded-green dot. */
export function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-header backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span
            aria-hidden
            className="h-2 w-2 rounded-full bg-grounded shadow-[0_0_8px_rgba(28,122,77,0.5)]"
          />
          <span className="font-mono text-[13px] font-medium tracking-[0.2em] text-ink">
            GROUNDCITE
          </span>
        </Link>

        <nav aria-label="Primary" className="flex gap-6 text-sm">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "-mb-3 border-b-2 border-accent pb-3 text-accent"
                    : "-mb-3 border-b-2 border-transparent pb-3 text-ink/60 transition-colors hover:text-ink"
                }
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
