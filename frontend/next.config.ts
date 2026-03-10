import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  experimental: {
    serverActions: {
      bodySizeLimit: "250mb",
    },
  },
};

export default nextConfig;