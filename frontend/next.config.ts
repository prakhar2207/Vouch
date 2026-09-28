import path from "path";
import withSerwistInit from "@serwist/next";
import type { NextConfig } from "next";

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  additionalPrecacheEntries: [
    { url: "/~offline", revision: "v1" },
  ],
  disable: process.env.NODE_ENV === "development",
});

const nextConfig: NextConfig = {
  turbopack: {},
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
