import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // Proxy API calls to the backend so cookies stay same-origin.
    // BACKEND_INTERNAL_URL overrides; otherwise production builds target the
    // hosted backend and dev builds target localhost. (`||` so an empty env
    // var also falls through.)
    const backend =
      process.env.BACKEND_INTERNAL_URL ||
      (process.env.NODE_ENV === "production"
        ? "https://aegis-backend-five.vercel.app"
        : "http://localhost:8000");
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
