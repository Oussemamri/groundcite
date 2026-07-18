/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // AD-3 (Week 4): proxy the API through Next's dev/prod server so the
  // browser only ever talks same-origin -- no CORS middleware needed on the
  // API, and this is also the production shape (reverse proxy). Falls back
  // to localhost:8000 (uvicorn's default) when API_ORIGIN isn't set.
  async rewrites() {
    const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
      // Week 6: the /ask chat theme's composer + run-detail panel show the
      // real running τ_retrieval (an honesty signal, not a guess) --
      // /healthz already exposes it but lives outside /api/v1, so it needs
      // its own same-origin proxy rule (AD-3's rationale applies equally
      // here: zero CORS, same production reverse-proxy shape).
      {
        source: "/healthz",
        destination: `${apiOrigin}/healthz`,
      },
    ];
  },
};

export default nextConfig;
