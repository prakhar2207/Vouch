# SRI LEKH — STAGE 1.1: PUBLIC ROUTE QA, SEO, ACCESSIBILITY & BUILD VERIFICATION

**Verification Date:** 2026-11-12  
**Live Server Mode:** Next.js `16.3.8` Production Build (`npm run build` + `next start -p 3101`)  
**Browser Engine:** Microsoft Edge (`Playwright` headless Chromium channel `msedge`)  
**Viewports Tested:** Desktop `1280×900` and Mobile `375×812`

---

## 1. Automated Verification Commands (Post-Final-Edit Results)

All frontend checks below were executed cleanly **after** the final Stage 1.1 edit to `frontend/src/lib/pwa/sw-cache-policy.ts`:

| Command | Scope | Exit Code | Exact Result |
| :--- | :--- | :--- | :--- |
| `npm test` (`frontend/`) | `node --import ./test-loader.mjs --test "src/**/*.test.ts"` | `0` | **23 / 23 tests passed, 0 failed, 0 skipped** (Contact form validation & mailto handoff: 6/6; Service Worker Cache Policy: 3/3; Offline-First Sync & Tenant/User Isolation: 5/5; Domain Role Capabilities Matrix: 4/4; Auth & Permission Utilities: 3/3 — 23 total assertions across 3 `.test.ts` files). |
| `npx tsc --noEmit` (`frontend/`) | Full frontend TypeScript project | `0` | **0 errors.** |
| `npx eslint src/lib/pwa/ src/app/sw.ts src/app/robots.ts src/app/sitemap.ts src/components/public/ src/app/pricing/ src/app/contact/ src/app/privacy-policy/ src/app/terms/ src/app/refund-policy/` | All Step 1 & Stage 1.1 public/PWA source files | `0` | **0 errors, 0 warnings.** |
| `npm run build` (`frontend/`) | Full webpack + Serwist SW production build | `0` | **Succeeded.** Compiled 56/56 static pages, generated `public/sw.js`, `/robots.txt`, `/sitemap.xml`. |
| `npm run lint` (`frontend/`) | Entire frontend repo (including untouched files) | `1` | Pre-existing lint baseline debt: **3,067 problems (1,075 errors, 1,992 warnings)** in untouched legacy/third-party files (e.g., `public/pdf.worker.min.mjs`, pre-existing ERP files). Zero errors in Stage 1.1 files. |

### Backend Reference Runs (Executed Earlier in Session on Isolated `test_db.sqlite3`)
- `python manage.py test apps.accounts.tests apps.accounts.tests_auth_otp apps.companies.tests apps.audit.tests apps.gst.tests apps.inventory.tests --verbosity=1`: **41 / 41 passed** (`exit 0`, 26.747s).
- `python manage.py test apps.accounting.tests apps.accounting.tests_financial_reports apps.accounting.tests_cash_and_allocation apps.inventory.tests_stage4_15_inventory apps.notifications.tests_stage4_15_auth --verbosity=1`: **28 / 29 passed, 1 error** (`test_concurrent_sales_deduct_stock_without_lost_update` hit SQLite `OperationalError: database table is locked: accounting_vouchersequence` because `settings.py` overrides PostgreSQL to local SQLite during `manage.py test`, which cannot handle multi-thread concurrent write locks).

---

## 2. Live Route & Playwright (`msedge`) Browser QA Matrix

| Route / Endpoint | HTTP Status | Title Present | Canonical Link | H1 Count | Desktop (`1280×900`) Overflow | Mobile (`375×812`) Overflow | Broken `<img>` | Page Errors | Console Errors |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/` | `200` | `SriLekh - Double-Entry Accounting & AI ERP` | `null` *(root `layout.tsx` omits route canonical)* | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `1` (`net::ERR_CONNECTION_REFUSED` when local Django API `:8000` is off) |
| `/pricing` | `200` | `SriLekh Pricing \| Accounting Software for Indian Businesses` | `https://srilekh.com/pricing` | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `0` |
| `/contact` | `200` | `Contact SriLekh \| Business Support` | `https://srilekh.com/contact` | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `0` |
| `/privacy-policy` | `200` | `Privacy Policy \| SriLekh` | `https://srilekh.com/privacy-policy` | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `0` |
| `/terms` | `200` | `Terms and Conditions \| SriLekh` | `https://srilekh.com/terms` | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `0` |
| `/refund-policy` | `200` | `Refund Policy \| SriLekh` | `https://srilekh.com/refund-policy` | `1` | `0px` (`1280 <= 1280`) | `0px` (`375 <= 375`) | `0 / 2` | `0` | `0` |
| `/robots.txt` | `200` | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/sitemap.xml` | `200` | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/manifest.webmanifest` | `200` | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `/sw.js` | `200` | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

### Additional Browser & DOM Observations
- **Header & Footer Navigation:** All 6 pages expose consistent navigation, `<PublicFooter />` links to `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `mailto:support@srilekh.com`, `/~offline`, and ERP links (`/dashboard`, `/sales`, `/purchases`, `/vouchers`).
- **Keyboard Accessibility:** Sequential `Tab` navigation moves focus cleanly onto anchor links (`Keyboard Shortcuts` on `/`, `Contact` on public subpages). On `/contact`, all 7 form labels (`contact-company-website`, `contact-full-name`, `contact-email`, `contact-phone`, `contact-business`, `contact-subject`, `contact-message`) map `htmlFor` to an existing DOM input ID (`inputExists: true`).
- **Contact Form E2E Test in Headless Edge:**
  - Submitting empty form triggered `[role="alert"]` validation cleanly without submitting.
  - Waiting > 2s and submitting valid data rendered `[role="status"]`: `"Not yet sent — send this prepared draft using your email application..."` plus valid `mailto:support@srilekh.com?subject=...&body=...` link (length `373 <= 1900`).
- **Minor SEO Observation (Low Risk / P3):** `/pricing`, `/contact`, `/privacy-policy`, `/terms`, and `/refund-policy` inherit root `openGraph.title` and `openGraph.description` (`"SriLekh - Double-Entry Accounting & AI ERP"`) from [`frontend/src/app/layout.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/layout.tsx) rather than defining route-specific `openGraph` blocks. Adding `openGraph` per route and `canonical: "/"` on `page.tsx` can be done cleanly in a future polish commit.

---

## 3. Service Worker (`public/sw.js`) & Crawler Audit

- **`public/sw.js` Bundle Verification (`57,727` bytes):**
  - Compiled regex guards verified inside production bundle: `[/^api\.srilekh\.com$/i,/^api-staging\.srilekh\.com$/i,/\.onrender\.com$/i]`, `8000` localhost check, and `Authorization` header guard routed to `NetworkOnly`.
  - Filter set `new Set(["cross-origin","apis","static-data-assets","next-data","pages","pages-rsc","pages-rsc-prefetch","others"])` strips Serwist's unsafe default entries at SW startup.
  - `activate` and `CLEAR_SESSION_CACHES` handlers wipe legacy `vouch`/`shrilekh` prefixes as well as `"srilekh-static-icons"`, `"cross-origin"`, `"apis"`, `"static-data-assets"`, `"next-data"`, `"others"`, and `"srilekh-pages-cache"`.
- **`/robots.txt`:** Explicitly allows `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/login`, `/register`; explicitly disallows internal routes (`/admin`, `/dashboard`, `/sales`, `/purchases`, `/vouchers`, `/banking`, `/ledgers`, `/parties`, `/inventory`, `/reports`, `/gst`, `/settings`, `/audit`, `/analytics`, `/import`, `/export`, `/network`, `/claim`, `/share`, `/api`); declares `Sitemap: https://srilekh.com/sitemap.xml`.
- **`/sitemap.xml`:** Lists strictly the 6 public URLs (`/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`) under `https://srilekh.com`.
- **Baseline PDF Note:** `SriLekh_Public_Compliance_Pages.pdf` reflects Step 1 content prior to Stage 1.1 copy/policy updates and should be regenerated before sharing externally.
