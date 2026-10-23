import path from "path";
import withSerwistInit from "@serwist/next";
import type { NextConfig } from "next";

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  additionalPrecacheEntries: [
    { url: "/~offline", revision: "v2" },
    { url: "/dashboard", revision: "v2" },
    { url: "/sales", revision: "v2" },
    { url: "/sales/new", revision: "v2" },
    { url: "/ledgers", revision: "v2" },
    { url: "/parties", revision: "v2" },
    { url: "/inventory", revision: "v2" },
    { url: "/login", revision: "v2" },
  ],
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  turbopack: {},
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(self), microphone=(), geolocation=(), browsing-topics=()',
          },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' data: https://fonts.gstatic.com",
              "img-src 'self' data: blob: https:",
              "connect-src 'self' https://api.srilekh.com https://*.srilekh.com https://vouch-api-752s.onrender.com https://*.onrender.com http://localhost:8000 http://127.0.0.1:8000 ws: wss:",
              "worker-src 'self' blob:",
              "frame-ancestors 'none'",
            ].join('; '),
          },
        ],
      },
    ];
  },
  webpack: (config) => {
    // Force webpack to resolve html2canvas to the patched non-minified ESM file.
    // Our patch-html2canvas.js script removes the "throw Error" for unsupported
    // color functions (oklab, oklch, color-mix) that Tailwind v4 emits.
    // Without this alias, webpack may resolve to html2canvas.min.js which
    // can remain unpatched in CI environments with cached node_modules.
    config.resolve = config.resolve || {};
    config.resolve.alias = config.resolve.alias || {};
    (config.resolve.alias as Record<string, string>)["html2canvas"] = path.resolve(
      __dirname,
      "node_modules/html2canvas/dist/html2canvas.esm.js"
    );
    return config;
  },
};

export default withSerwist(nextConfig);
