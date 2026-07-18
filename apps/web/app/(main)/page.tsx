import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold">GroundCite</h1>
      <p className="mt-2 text-text/70">
        Grounded Q&amp;A over aerospace &amp; engineering standards — with exact clause citations.
      </p>
      <Link
        href="/ask"
        className="mt-8 inline-block rounded border border-link px-4 py-2 text-link transition-colors hover:bg-link/10"
      >
        Ask a question →
      </Link>
    </main>
  );
}
