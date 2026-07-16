"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/ask", label: "Ask" },
  { href: "/library", label: "Library" },
  { href: "/evals", label: "Evals" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span aria-hidden className="h-2 w-2 rounded-full bg-grounded" />
          <span className="font-mono text-sm font-medium tracking-[0.2em] text-text">
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
                    ? "border-b-2 border-link pb-3 -mb-3 text-link"
                    : "border-b-2 border-transparent pb-3 -mb-3 text-text/60 transition-colors hover:text-text"
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
