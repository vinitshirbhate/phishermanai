/** @type {import('next').NextConfig} */
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Proxy the API through Next so the browser makes same-origin requests and
  // no CORS configuration is needed for local development.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/:path*` },
    ];
  },
};

export default nextConfig;
