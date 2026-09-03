/// <reference lib="webworker" />
import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry } from "@serwist/precaching";
import { installSerwist } from "@serwist/sw";
import {
  BackgroundSyncPlugin,
  CacheFirst,
  ExpirationPlugin,
  NetworkOnly,
  StaleWhileRevalidate,
  type RuntimeCaching,
} from "serwist";

declare global {
  interface WorkerGlobalScope {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

// Background Sync Plugin for queued voucher mutations
const bgSyncPlugin = new BackgroundSyncPlugin("vouch-outbox-sync", {
  maxRetentionTime: 24 * 60, // Retry for max of 24 Hours (in minutes)
});

// Accounting custom runtime caching strategies
const accountingCustomCaching: RuntimeCaching[] = [
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

  // 2. Masters Data Routes (StaleWhileRevalidate)
  // Covers master sync, ledgers list, companies profile, and product inventory catalog
  {
    matcher: /\/api\/(?:v1\/)?(?:sync\/masters|ledgers|companies|inventory)(?:\/.*)?$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "vouch-masters-cache",
      plugins: [
        new ExpirationPlugin({
          maxEntries: 50,
          maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
        }),
      ],
    }),
  },

  // 3. Voucher Mutation Routes (NetworkOnly with Background Sync outbox fallback)
  {
    matcher: /\/api\/(?:v1\/)?(?:vouchers\/sync|attachments\/upload|vouchers\/?)$/i,
    method: "POST",
    handler: new NetworkOnly({
      plugins: [bgSyncPlugin],
    }),
  },
];

// Precache Critical Application Shell Routes
const criticalShellEntries: PrecacheEntry[] = [
  { url: "/dashboard", revision: "v1.1" },
  { url: "/vouchers/new", revision: "v1.1" },
  { url: "/vouchers/grid", revision: "v1.1" },
  { url: "/parties", revision: "v1.1" },
  { url: "/sales", revision: "v1.1" },
  { url: "/purchases", revision: "v1.1" },
  { url: "/settings", revision: "v1.1" },
  { url: "/~offline", revision: "v1.1" },
];

const manifestEntries = (self.__SW_MANIFEST || []).concat(criticalShellEntries);

installSerwist({
  precacheEntries: manifestEntries,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [...accountingCustomCaching, ...defaultCache],
  fallbacks: {
    entries: [
      {
        url: "/~offline",
        matcher({ request }: any) {
          return request.destination === "document";
        },
      } as any,
    ],
  },
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
