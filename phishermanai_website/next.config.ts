import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// Pin the workspace root: a stray lockfile on the drive above otherwise makes
// Turbopack infer D:\ as the project root.
const projectRoot = path.dirname(fileURLToPath(import.meta.url));

// Standalone output is for self-hosting (Docker) only. On Vercel it breaks the
// build: the standalone copy step reads .next/next-server.js.nft.json, which
// Vercel's pipeline does not leave behind, so the build dies with ENOENT.
// Vercel traces and bundles the server itself, so it needs nothing here.
const isVercel = Boolean(process.env.VERCEL);

const nextConfig: NextConfig = {
  ...(isVercel ? {} : { output: "standalone" as const }),
  poweredByHeader: false,
  compress: true,
  productionBrowserSourceMaps: false,
  images: {
    formats: ["image/avif", "image/webp"],
  },
  turbopack: {
    root: projectRoot,
  },
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "motion"],
  },
  async redirects() {
    return [
      { source: "/product/email", destination: "/#channel-email", permanent: true },
      { source: "/product/voice", destination: "/#channel-voice", permanent: true },
      { source: "/product/video", destination: "/#channel-video", permanent: true },
      { source: "/product/social", destination: "/#channel-social", permanent: true },
      { source: "/product/extension", destination: "/#channel-web", permanent: true },
      { source: "/product/authenticity", destination: "/#authenticity", permanent: true },
    ];
  },
};

export default nextConfig;
