import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold text-ink">GroundCite</h1>
      <p className="mt-2 text-ink/70">
        Grounded Q&amp;A over aerospace &amp; engineering standards — with exact clause citations.
      </p>
      <Link
        href="/ask"
        className="mt-8 inline-block rounded-md border border-accent/45 bg-accent/[0.06] px-4 py-2 text-accent transition-colors hover:bg-accent/[0.14]"
      >
        Ask a question →
      </Link>
    </main>
  );
}
