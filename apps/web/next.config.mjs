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
    ];
  },
};

export default nextConfig;
