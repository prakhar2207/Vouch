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
  // 0. Navigation / Documents (NetworkFirst with offline fallback via Serwist fallbacks config)
  {
    matcher: ({ request, url }: any) => {
      // Never intercept API calls or backend endpoints
      if (url.pathname.startsWith("/api/")) return false;
      return request.mode === "navigate" || request.destination === "document";
    },
    handler: new NetworkFirst({
      cacheName: "vouch-pages-cache",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 50,
          maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
        }),
      ],
    }),
  },

  // 1. Static Assets & Fonts (CacheFirst)
  {
    matcher: /\/_next\/static\/.+\.(?:js|css)$/i,
    handler: new CacheFirst({
      cacheName: "vouch-static-assets",
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
      cacheName: "vouch-static-icons",
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

// Cache cleanup: Wipe obsolete vouch-masters-cache from any existing clients
self.addEventListener("activate", (event: any) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((cacheName) => cacheName.includes("vouch-masters-cache"))
          .map((cacheName) => caches.delete(cacheName))
      );
    })
  );
});

// Service Worker Background Sync Event Listener
self.addEventListener("sync", (event: any) => {
  if (event.tag === "vouch-outbox-sync") {
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
    body: data.body || 'You have a new alert in Vouch.',
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

