/**
 * Service Worker cache-safety helpers for SriLekh PWA.
 * Enforces strict separation between public/static shell assets and
 * authenticated financial/API/session data.
 */

export const SENSITIVE_CACHE_NAMES = [
  "srilekh-pages-cache",
  "pages",
  "pages-rsc",
  "pages-rsc-prefetch",
  "cross-origin",
  "apis",
  "next-data",
  "static-data-assets",
  "others",
] as const;

const LEGACY_CACHE_PREFIXES = ["vouch", "shrilekh"] as const;

const UNSAFE_DEFAULT_CACHE_NAMES = new Set<string>([
  "cross-origin",
  "apis",
  "static-data-assets",
  "next-data",
  "pages",
  "pages-rsc",
  "pages-rsc-prefetch",
  "others",
]);

const API_BACKEND_HOST_PATTERNS = [
  /^api\.srilekh\.com$/i,
  /^api-staging\.srilekh\.com$/i,
  /\.onrender\.com$/i,
];

export function isSensitiveOrApiUrl(urlInput: string | URL): boolean {
  try {
    const parsed = typeof urlInput === "string" ? new URL(urlInput, "https://srilekh.com") : urlInput;
    if (parsed.pathname.startsWith("/api/")) {
      return true;
    }
    if (API_BACKEND_HOST_PATTERNS.some((re) => re.test(parsed.hostname))) {
      return true;
    }
    if (
      (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") &&
      parsed.port === "8000"
    ) {
      return true;
    }
    return false;
  } catch {
    return true;
  }
}

export function isSensitiveOrApiRequest(params: {
  url: string | URL;
  hasAuthorizationHeader?: boolean;
}): boolean {
  if (params.hasAuthorizationHeader) {
    return true;
  }
  return isSensitiveOrApiUrl(params.url);
}

export function shouldPurgeCacheOnActivate(cacheName: string): boolean {
  if (LEGACY_CACHE_PREFIXES.some((prefix) => cacheName.includes(prefix))) {
    return true;
  }
  if (cacheName === "srilekh-static-icons") {
    return true;
  }
  // Remove legacy unsafe caches from older Service Worker versions
  return (
    cacheName === "cross-origin" ||
    cacheName === "apis" ||
    cacheName === "static-data-assets" ||
    cacheName === "next-data" ||
    cacheName === "others"
  );
}

export function shouldPurgeCacheOnLogout(cacheName: string): boolean {
  return (
    (SENSITIVE_CACHE_NAMES as readonly string[]).includes(cacheName) ||
    cacheName.includes("srilekh") ||
    cacheName.includes("vouch") ||
    cacheName.includes("pages") ||
    cacheName.includes("cross-origin") ||
    cacheName.includes("apis")
  );
}

export interface DefaultCacheLikeEntry {
  matcher?: unknown;
  handler?: unknown;
}

export function filterSafeDefaultCache<T extends DefaultCacheLikeEntry>(entries: T[]): T[] {
  return entries.filter((entry) => {
    if (entry.matcher instanceof RegExp && entry.matcher.toString() === "/.*/i") {
      return false;
    }
    const handlerObj =
      entry.handler && typeof entry.handler === "object"
        ? (entry.handler as { cacheName?: unknown })
        : undefined;
    const cacheName = typeof handlerObj?.cacheName === "string" ? handlerObj.cacheName : undefined;
    if (cacheName && UNSAFE_DEFAULT_CACHE_NAMES.has(cacheName)) {
      return false;
    }
    return true;
  });
}
