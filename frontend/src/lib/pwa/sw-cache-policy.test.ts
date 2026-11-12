import test from "node:test";
import assert from "node:assert/strict";
import {
  filterSafeDefaultCache,
  isSensitiveOrApiRequest,
  isSensitiveOrApiUrl,
  shouldPurgeCacheOnActivate,
  shouldPurgeCacheOnLogout,
  type DefaultCacheLikeEntry,
} from "./sw-cache-policy";

test("Service Worker Cache Policy & Session Isolation", async (t) => {
  await t.test("identifies all API, backend, and Authorization-bearing requests as sensitive", () => {
    assert.equal(isSensitiveOrApiUrl("https://srilekh.com/api/v1/companies/"), true);
    assert.equal(isSensitiveOrApiUrl("https://api.srilekh.com/api/v1/accounting/vouchers/"), true);
    assert.equal(isSensitiveOrApiUrl("https://vouch-api-752s.onrender.com/api/health/"), true);
    assert.equal(isSensitiveOrApiUrl("http://127.0.0.1:8000/api/v1/auth/me/"), true);
    assert.equal(
      isSensitiveOrApiRequest({
        url: "https://srilekh.com/dashboard",
        hasAuthorizationHeader: true,
      }),
      true
    );

    assert.equal(isSensitiveOrApiUrl("https://srilekh.com/privacy-policy"), false);
    assert.equal(isSensitiveOrApiUrl("https://srilekh.com/_next/static/chunks/app.js"), false);
  });

  await t.test("strips cross-origin, apis, pages-rsc, and dynamic data strategies from defaultCache", () => {
    const sampleDefaultCache: DefaultCacheLikeEntry[] = [
      { handler: { cacheName: "google-fonts-webfonts" } },
      { handler: { cacheName: "static-image-assets" } },
      { handler: { cacheName: "static-js-assets" } },
      { handler: { cacheName: "static-style-assets" } },
      { handler: { cacheName: "cross-origin" } },
      { handler: { cacheName: "apis" } },
      { handler: { cacheName: "static-data-assets" } },
      { handler: { cacheName: "next-data" } },
      { handler: { cacheName: "pages-rsc" } },
      { handler: { cacheName: "pages-rsc-prefetch" } },
      { handler: { cacheName: "pages" } },
      { handler: { cacheName: "others" } },
      { matcher: /.*/i, handler: { cacheName: "fallback" } },
    ];

    const filtered = filterSafeDefaultCache(sampleDefaultCache);
    const remainingNames = filtered.map((e) => e.handler?.cacheName);

    assert.deepEqual(remainingNames, [
      "google-fonts-webfonts",
      "static-image-assets",
      "static-js-assets",
      "static-style-assets",
    ]);
  });

  await t.test("purges legacy and cross-origin caches on activate and logout", () => {
    assert.equal(shouldPurgeCacheOnActivate("cross-origin"), true);
    assert.equal(shouldPurgeCacheOnActivate("apis"), true);
    assert.equal(shouldPurgeCacheOnActivate("vouch-pages-cache"), true);
    assert.equal(shouldPurgeCacheOnActivate("srilekh-static-icons-v2"), false);

    assert.equal(shouldPurgeCacheOnLogout("srilekh-pages-cache"), true);
    assert.equal(shouldPurgeCacheOnLogout("cross-origin"), true);
    assert.equal(shouldPurgeCacheOnLogout("pages-rsc"), true);
    assert.equal(shouldPurgeCacheOnLogout("apis"), true);
    assert.equal(shouldPurgeCacheOnLogout("google-fonts-webfonts"), false);
  });
});
