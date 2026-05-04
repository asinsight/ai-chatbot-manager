/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    serverActions: {
      allowedOrigins: ["127.0.0.1:9000", "localhost:9000"],
    },
  },
};

export default nextConfig;
