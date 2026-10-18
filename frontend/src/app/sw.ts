/// <reference lib="webworker" />
import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry } from "@serwist/precaching";
import { installSerwist } from "@serwist/sw";
import {
  CacheFirst,
  ExpirationPlugin,
  NetworkFirst,
  type RuntimeCaching,
} from "serwist";

declare global {
  interface WorkerGlobalScope {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

// Filter defaultCache so catch-all matchers do NOT intercept backend API or cross-origin calls
const safeDefaultCache = defaultCache.filter((entry) => {
  if (entry.matcher instanceof RegExp && entry.matcher.toString() === "/.*/i") {
    return false;
  }
  return true;
});

// Accounting custom runtime caching strategies
// RULE: Service Worker must NEVER intercept, cache, or modify authenticated accounting API requests
// (e.g., /api/v1/companies/, /api/v1/sync/, onrender.com backend, etc.)
// All offline financial data is managed authoritatively via IndexedDB (Dexie).
const accountingCustomCaching: RuntimeCaching[] = [
  // 0. Navigation / Documents (NetworkFirst with offline fallback)
  {
    matcher: ({ request, url }: any) => {
      // Never intercept API calls or backend endpoints
      if (url.pathname.startsWith("/api/")) return false;
      return request.mode === "navigate" || request.destination === "document";
    },
    handler: new NetworkFirst({
      cacheName: "srilekh-pages-cache",
      networkTimeoutSeconds: 2,
      plugins: [
        new ExpirationPlugin({
          maxEntries: 60,
          maxAgeSeconds: 14 * 24 * 60 * 60, // 14 days
        }),
        {
          handlerDidError: async ({ request }: any) => {
            try {
              // 1. Try exact match from cache first
              const exactMatch = await caches.match(request);
              if (exactMatch) return exactMatch;

              const reqUrl = request?.url || "";

              // 2. Intelligent route-specific fallbacks
              if (reqUrl.includes("/sales/new")) {
                const salesNew = await caches.match("/sales/new");
                if (salesNew) return salesNew;
              }
              if (reqUrl.includes("/sales")) {
                const sales = await caches.match("/sales");
                if (sales) return sales;
              }
              if (reqUrl.includes("/dashboard")) {
                const dash = await caches.match("/dashboard");
                if (dash) return dash;
              }
              if (reqUrl.includes("/inventory")) {
                const inv = await caches.match("/inventory");
                if (inv) return inv;
              }
              if (reqUrl.includes("/parties") || reqUrl.includes("/ledgers")) {
                const parties = await caches.match("/parties") || await caches.match("/ledgers");
                if (parties) return parties;
              }

              // 3. Fallback to cached dedicated offline page
              const cachedOffline = await caches.match("/~offline");
              if (cachedOffline) return cachedOffline;
            } catch {}

            return new Response(
              `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SriLekh - Offline Mode</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0F172A; color: #F8FAFC; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; text-align: center; }
    .card { background: #1E293B; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 28px; max-width: 360px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
    .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); color: #FBBF24; font-size: 11px; font-weight: 700; margin-bottom: 12px; }
    h2 { font-size: 20px; margin: 0 0 8px; font-weight: 800; }
    p { font-size: 13px; color: #94A3B8; line-height: 1.5; margin: 0 0 20px; }
    .btn { display: block; width: 100%; box-sizing: border-box; background: #2563EB; color: #fff; text-decoration: none; padding: 12px; border-radius: 10px; font-weight: 700; font-size: 14px; margin-bottom: 10px; }
    .btn-secondary { background: rgba(255,255,255,0.08); color: #E2E8F0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">⚡ OFFLINE MODE</div>
    <h2>SriLekh Offline</h2>
    <p>Your local accounting engine is operational. You can continue creating sales invoices without internet.</p>
    <a href="/sales/new" class="btn">📝 Create Sales Invoice</a>
    <a href="/sales" class="btn btn-secondary">📋 View Sales</a>
    <a href="/dashboard" class="btn btn-secondary">📊 Dashboard</a>
  </div>
</body>
</html>`,
              { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } }
            );
          },
        },
      ],
    }),
  },

  // 1. Static Assets & Fonts (CacheFirst)
  {
    matcher: /\/_next\/static\/.+\.(?:js|css)$/i,
    handler: new CacheFirst({
      cacheName: "srilekh-static-assets",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 120,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        }),
      ],
    }),
  },
  {
    matcher: /\.(?:png|jpg|jpeg|svg|ico|webp)$/i,
    handler: new CacheFirst({
      cacheName: "srilekh-static-icons-v2",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 64,
          maxAgeSeconds: 30 * 24 * 60 * 60,
        }),
      ],
    }),
  },
];

installSerwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: false,
  runtimeCaching: [...accountingCustomCaching, ...safeDefaultCache],
  fallbacks: {
    entries: [
      {
        url: "/~offline",
        matcher({ request }: any) {
          return request.destination === "document" || request.mode === "navigate";
        },
      } as any,
    ],
  },
});

// Precache offline page on install
self.addEventListener("install", (event: any) => {
  event.waitUntil(
    caches.open("srilekh-pages-cache").then((cache) => cache.add("/~offline").catch(() => {}))
  );
});

// Cache cleanup: Wipe obsolete vouch, legacy shrilekh, and previous icon caches from existing clients
self.addEventListener("activate", (event: any) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => cacheName.includes("vouch") || cacheName.includes("shrilekh") || cacheName === "srilekh-static-icons")
          .map((cacheName) => caches.delete(cacheName))
      );
    })
  );
});

// Service Worker Background Sync Event Listener
self.addEventListener("sync", (event: any) => {
  if (event.tag === "srilekh-outbox-sync") {
    event.waitUntil(
      (async () => {
        const allClients = await self.clients.matchAll({
          type: "window",
          includeUncontrolled: true,
        });
        for (const client of allClients) {
          client.postMessage({ type: "TRIGGER_OUTBOX_SYNC" });
        }
      })()
    );
  }
});


self.addEventListener('push', (event: any) => {
  let data: any = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'New Notification';
  const options = {
    body: data.body || 'You have a new alert in SriLekh.',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-192x192.png',
    data: {
      url: data.url || '/network/inbox',
    },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event: any) => {
  event.notification.close();
  const urlToOpen = new URL(event.notification.data.url, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      let matchingClient = null;
      for (let i = 0; i < windowClients.length; i++) {
        const windowClient = windowClients[i];
        if (windowClient.url === urlToOpen) {
          matchingClient = windowClient;
          break;
        }
      }
      if (matchingClient) {
        return matchingClient.focus();
      } else {
        return self.clients.openWindow(urlToOpen);
      }
    })
  );
});

