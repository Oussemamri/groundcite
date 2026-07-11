import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold">GroundCite</h1>
      <p className="mt-2 text-text/70">
        Grounded Q&amp;A over aerospace &amp; engineering standards — with exact clause citations.
      </p>
      <nav className="mt-8 flex gap-4 text-link">
        <Link href="/ask">Ask</Link>
        <Link href="/library">Library</Link>
        <Link href="/evals">Evals</Link>
      </nav>
    </main>
  );
}
