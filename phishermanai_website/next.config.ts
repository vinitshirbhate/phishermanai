import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// Pin the workspace root: a stray lockfile on the drive above otherwise makes
// Turbopack infer D:\ as the project root.
const projectRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: {
    root: projectRoot,
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
