import { Nav } from "@/app/components/Nav";

/**
 * Every page except `/ask` (spec §2.2 warm paper theme, shared top nav).
 * `/ask` deliberately lives outside this route group — its own
 * full-viewport chat shell replaces the top nav with its sidebar's wordmark
 * row instead. Route groups don't affect URLs: `/library`, `/evals`,
 * `/documents/[slug]`, and `/` are unchanged.
 */
export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      {children}
    </>
  );
}
