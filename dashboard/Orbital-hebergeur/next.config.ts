import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep in sync with src/lib/panel-base.ts
  basePath: "/hebergement",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async redirects() {
    return [
      {
        source: "/",
        destination: "/hebergement",
        permanent: false,
        basePath: false,
      },
    ];
  },
};

export default nextConfig;
