# Frontend Responsiveness & Caching Improvement Plan

## 1️⃣ Responsive UI Fixes

| Area | Issue | Recommended Fix |
|------|-------|----------------|
| **Viewport** | Missing meta tag may cause scaling issues on mobile. | Add `<meta name="viewport" content="width=device-width, initial-scale=1" />` in a custom `_document.tsx`. |
| **Layout** | Many components use fixed widths / heights that break on smaller screens. | Replace fixed pixel values with responsive Tailwind utilities (`w-full`, `max-w-screen-md`, `grid-cols-1 md:grid-cols-2`, etc.). |
| **Images / Icons** | Large raster images are not scaled. | Use Next.js `<Image>` component with `layout="responsive"` or Tailwind `object-contain`. |
| **Typography** | Font sizes are static. | Apply responsive text classes (`text-sm md:text-base lg:text-lg`). |
| **Breakpoints** | No explicit breakpoint handling in custom modals (e.g., `PurchaseOrderDraftModal`). | Wrap modal containers with Tailwind responsive classes (`sm:w-11/12 md:w-3/4 lg:w-1/2`). |

### Quick Code Snippets

#### `pages/_document.tsx`
```tsx
import Document, { Html, Head, Main, NextScript } from 'next/document';

export default class MyDocument extends Document {
  render() {
    return (
      <Html>
        <Head>
          {/* Responsive viewport meta tag */}
          <meta name="viewport" content="width=device-width, initial-scale=1" />
        </Head>
        <body>
          <Main />
          <NextScript />
        </body>
      </Html>
    );
  }
}
```

#### Example Modal Responsiveness (`components/modals/PurchaseOrderDraftModal.tsx`)
```tsx
<div className="fixed inset-0 flex items-center justify-center p-4">
  <div className="bg-white rounded-lg shadow-xl w-full max-w-md sm:max-w-lg lg:max-w-xl">
    {/* modal content */}
  </div>
</div>
```

## 2️⃣ Caching & Local‑First Architecture

| Concern | Current State | Fix |
|---------|---------------|-----|
| **Service Worker** | Custom `sw.js` does not precache Next.js runtime assets, causing a full network load each visit. | Replace with **next‑pwa** (uses Workbox) to automatically precache static assets, chunks, and runtime routes. |
| **Static Assets** | Images, fonts, JS bundles are fetched on every load. | Add `runtimeCaching` rules for images, fonts, and API responses. |
| **Local Analytics Engine** | `LocalAnalyticsEngine` reads from IndexedDB but UI still waits for network fetch before showing data. | Pre‑populate IndexedDB on first visit using the service worker's `backgroundSync` queue or `precacheAndRoute` with a custom handler that writes the initial dataset. |
| **PWA Manifest** | Not present, so offline install prompt is missing. | Add `public/manifest.json` and enable `next-pwa` `manifest` option. |

### Implementation Steps
1. **Install dependencies**
   ```bash
   cd C:/Users/prakh/OneDrive/Desktop/projects/B2B
   npm i next-pwa workbox-window
   ```
2. **Create `next-pwa.config.js`**
```js
// next-pwa.config.js
module.exports = {
  dest: 'public',
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === 'development',
  runtimeCaching: [
    {
      urlPattern: /^https?.*\.(?:png|jpg|jpeg|svg|gif|webp)$/i,
      handler: 'CacheFirst',
      options: {
        cacheName: 'static-image-assets',
        expiration: { maxEntries: 100, maxAgeSeconds: 30 * 24 * 60 * 60 },
      },
    },
    {
      urlPattern: /^https?.*\.(?:js|css)$/i,
      handler: 'StaleWhileRevalidate',
      options: { cacheName: 'static-js-css', expiration: { maxEntries: 200, maxAgeSeconds: 7 * 24 * 60 * 60 } },
    },
    // API fallback – network first, cache on success
    {
      urlPattern: /\/api\//,
      handler: 'NetworkFirst',
      options: { cacheName: 'api-responses', networkTimeoutSeconds: 5, expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 } },
    },
  ],
};
```
3. **Update `next.config.js`**
```js
const withPWA = require('next-pwa')({
  dest: 'public',
  // Import config from the file above
  ...require('./next-pwa.config'),
});
module.exports = withPWA({
  // existing Next.js config …
});
```
4. **Add `manifest.json`** (`public/manifest.json`)
```json
{
  "name": "Vouch",
  "short_name": "Vouch",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#0ea5e9",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```
5. **Register Service Worker in `_app.tsx`**
```tsx
import { useEffect } from 'react';
import { Workbox } from 'workbox-window';

function MyApp({ Component, pageProps }) {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      const wb = new Workbox('/sw.js');
      wb.register();
    }
  }, []);

  return <Component {...pageProps} />;
}
export default MyApp;
```
6. **Pre‑seed IndexedDB**
   - Create a small script `scripts/seed-indexeddb.ts` that fetches the initial analytics payload (`/api/v1/analytics/initial/<cid>`) and writes to IndexedDB.
   - Call this script from a Service Worker `oninstall` hook using `workbox-background-sync` to ensure the seed runs even offline.

## 3️⃣ Expected Impact
- **UI** will adapt fluidly across mobile, tablet, and desktop (no overflow or broken layout). 
- **First‑load time** reduces from 30‑60 s to sub‑5 s after the service worker precaches static assets. 
- **Offline / PWA** capability is enabled; users can open the app without network and see cached analytics instantly. 
- **Local‑first** analytics engine will read from IndexedDB instantly, falling back to network only for fresh data.

---
**Next Steps**
1. Apply the responsive CSS changes to problem components (modals, tables, charts). 
2. Run the dependency install and configure `next-pwa` as described. 
3. Deploy and verify the service worker registers (check Chrome DevTools > Application > Service Workers). 
4. Test on mobile devices/emulators: first load should be cached, subsequent loads instantaneous.

Feel free to let me know which specific component’s layout you’d like me to adjust first, or if you want me to apply the PWA changes directly.
