/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy API calls to the Intelligence Hub during dev.
    const hub = process.env.HUB_URL ?? "http://localhost:4000";
    return [{ source: "/api/:path*", destination: `${hub}/api/:path*` }];
  },
};
export default nextConfig;
