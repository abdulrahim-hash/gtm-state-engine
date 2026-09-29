import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@gtm-state/contracts"],
};

export default nextConfig;
