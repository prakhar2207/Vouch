import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  // Generate a random cryptographically secure nonce (Base64)
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";

  // Strict CSP policy using nonce and strict-dynamic
  // 'strict-dynamic' allows scripts dynamically created by the nonce-authorized root scripts to load
  // 'self' and https: provide fallback for older browsers that do not support strict-dynamic
  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${isDev ? "'unsafe-eval'" : ""};
    style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
    img-src 'self' blob: data: https:;
    font-src 'self' data: https://fonts.gstatic.com;
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-ancestors 'none';
    worker-src 'self' blob:;
    connect-src 'self' https://api.srilekh.com https://*.srilekh.com https://vouch-api-752s.onrender.com https://*.onrender.com http://localhost:8000 http://127.0.0.1:8000 ws: wss:;
  `.replace(/\s{2,}/g, " ").trim();

  // Forward nonce and CSP to downstream Server Components and Client Components
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  // Set CSP and x-nonce on the outgoing HTTP response
  response.headers.set("Content-Security-Policy", cspHeader);
  response.headers.set("x-nonce", nonce);

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - sw.js / worker files
     */
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|workbox-.*).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
