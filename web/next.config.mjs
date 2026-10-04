/** @type {import('next').NextConfig} */
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
];

const nextConfig = {
  reactStrictMode: true,
  // Zero-downtime deploys: deploy/web-build.sh builds into .next-build while the
  // running server keeps serving .next, then swaps and restarts (see DEPLOY.md).
  // `next start` must run WITHOUT this variable so it serves the swapped-in .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,            // no "X-Powered-By: Next.js"
  compress: true,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};
export default nextConfig;
