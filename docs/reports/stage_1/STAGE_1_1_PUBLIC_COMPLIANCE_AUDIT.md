# SRI LEKH — STAGE 1.1: PUBLIC COMPLIANCE ACCURACY, PRIVACY VERIFICATION & LEGAL READINESS AUDIT

**Audit Date:** 2026-11-12  
**Branch / Base Commit:** `fix/stage4-12-day6-remediation` (`c15a64f` + Step 1 & Stage 1.1 public/PWA additions)  
**Scope:** Independent codebase & live-route audit and safe public-page/Service-Worker remediation covering `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/robots.txt`, `/sitemap.xml`, `ContactForm`, and `/sw.js`.  
**Baseline Reference:** `SriLekh_Public_Compliance_Pages.pdf` (Step 1 snapshot, prior to Stage 1.1 remediations).

---

## 1. Executive Summary

This Stage 1.1 audit cross-checked every technical, functional, privacy, security, commercial, and operational claim published across SriLekh's five public compliance pages and shared homepage footer against the actual Django backend (`apps/*`, `config/settings.py`), Next.js frontend (`frontend/src/*`), Serwist PWA configuration (`frontend/src/app/sw.ts`), Dexie offline database (`frontend/src/lib/db/offlineDb.ts`), CRDT/outbox sync worker (`frontend/src/lib/sync/sync-worker.ts`, `frontend/src/lib/crdt/*`), and live production server build (`next start`).

### Key Conclusions

1. **Critical Cache-Isolation Defect (P0) Found & Remediated in Public PWA Layer:**
   - `@serwist/next`'s `defaultCache` included runtime strategies named `cross-origin`, `apis`, `static-data-assets`, `next-data`, `pages-rsc`, `pages-rsc-prefetch`, `pages`, and `others`.
   - Because SriLekh calls backend APIs cross-origin (`api.srilekh.com`, `*.onrender.com`, or `localhost:8000`) and the prior filter in `frontend/src/app/sw.ts` only stripped `/.*/i`, cross-origin API GET responses could be cached into browser `CacheStorage` (`"cross-origin"`) and were not purged on logout (`CLEAR_SESSION_CACHES` only cleared `srilekh-pages-cache`).
   - **Remediated** via [`frontend/src/lib/pwa/sw-cache-policy.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/lib/pwa/sw-cache-policy.ts) and [`frontend/src/app/sw.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/sw.ts), verified by 3 unit tests and inspected inside the production webpack bundle `frontend/public/sw.js`.

2. **Public Disclosure Overstatements & Omissions Remediated (P1/P2):**
   - **`/pricing`:** Corrected overclaims around batch/serial deduction and alternate-unit invoice conversion (setup metadata exists on `Product` / `InventoryEntry`, but `StockService.process_voucher_stock` does not deduct per-batch/serial lots), GST live portal/E-Way Bill/E-Invoice status (`MockGSTProvider` & sandbox defaults; no live E-Way Bill dispatch, no E-Invoice URL route, live government return filing inactive), bank statement file scope (`.csv`, `.xlsx`, `.xls`, `.pdf`, `.ofx`, `.qif`; no live bank feed), and offline workflow boundaries (sales/purchase drafting & read caches vs online-only flows).
   - **`/privacy-policy`:** Added verified infrastructure/AI/storage disclosures including **Google Gemini API (`google.genai`)** for OCR purchase bills/bank statements/price lists, hosting/DB infrastructure (Vercel, Render, Neon PostgreSQL on AWS `ap-southeast-1`, Redis, SMTP/Gmail default, optional S3 `ap-south-1`, optional Cashfree GSP) with cross-border processing notice, exact client token/key storage (`access_token`/`refresh_token` non-`HttpOnly` JS cookies, `localStorage`, Capacitor `Preferences`, `VouchOfflineDB`, `VouchSecurityVault`), accurate shared-device logout behavior (read caches purged while unsynced `QUEUED`/`IN_FLIGHT`/`FAILED` outbox rows remain in IndexedDB tagged by `userId`/`companyId`), absence of self-serve permanent user deletion UI, and `BACKUP_RETENTION_DAYS` (`7` days default local archive pruning).
   - **`/refund-policy` & `/contact`:** Clarified that online payments cannot currently be made, distinguished future Razorpay procedures from active entitlements, added strict max-length + control-char/CRLF sanitization + `<= 1900`-char `mailto:` safety truncation with fallback copy warning, and stated explicitly that SriLekh cannot receive or guarantee delivery until the user's email client sends.
   - **Crawler Directives Added:** Created [`frontend/src/app/robots.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/robots.ts) and [`frontend/src/app/sitemap.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/sitemap.ts) to index only the 6 public pages (`/` plus 5 public compliance routes) and disallow internal ERP routes, `/share`, `/claim`, and `/api`.

3. **Remaining Hard Blockers Outside Engineering Control:**
   - Owner/Legal confirmations remain intentionally marked pending (registered legal entity name, physical registered office address matching KYC, verified support phone number, support hours, named Grievance Officer, pricing INR plans/GST/trial/refund windows, court jurisdiction city/state, processor DPAs, and deletion SLAs).
   - Non-public security hardening outside Step 1 scope (`auth.ts` storing JWTs in non-`HttpOnly` cookies & `localStorage`; `offlineDb.ts` logout `caches` loop missing `"cross-origin"`/`"apis"` directly alongside the `CLEAR_SESSION_CACHES` SW handler; SQLite multi-thread `VoucherSequence` locking limitation under unit tests vs PostgreSQL).

---

## 2. Prioritized Findings Register (P0 – P3)

| ID | Severity | Area | Finding Summary | Resolution / Status |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | **P0** | PWA / Service Worker Cache Isolation | `@serwist/next` `defaultCache` included `cross-origin`, `apis`, `static-data-assets`, `next-data`, `pages-rsc`, `pages-rsc-prefetch`, `pages`, `others`. Cross-origin authenticated API GETs could be cached by browser SW and left unpurged across sessions. | **Remediated** in `sw-cache-policy.ts` + `sw.ts`. Strips unsafe defaults, enforces `NetworkOnly` for `/api/`, `api.srilekh.com`, `*.onrender.com`, `localhost:8000`, and `Authorization` headers, purges legacy caches on `activate` and all session caches on `CLEAR_SESSION_CACHES`. |
| **F-02** | **P1** | `/privacy-policy` AI & Processor Transparency | Step 1 PDF omitted disclosure that uploaded purchase bills, scanned bank statements, and price lists can be sent to **Google Gemini (`google.genai`)**, and omitted Vercel/Render/Neon/Redis/SMTP/S3/international transfer disclosure. | **Remediated** in [`frontend/src/app/privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx) Section 8. |
| **F-03** | **P1** | `/privacy-policy` Local Logout Persistence Claim | Implied all local cached/offline data clears cleanly without stating that unsynchronized `QUEUED`/`IN_FLIGHT`/`FAILED` IndexedDB outbox items remain stored locally on the device (`userId`/`companyId` isolated) across logout. | **Remediated** in `privacy-policy/page.tsx` Section 10 + explicit shared-computer caution. |
| **F-04** | **P1** | `/privacy-policy` Token Storage & Deletion UI | Did not state that JWTs live in non-`HttpOnly` JS cookies, `localStorage`, and Capacitor `Preferences`, nor that self-serve permanent user deletion is absent in UI (`CompanyViewSet.destroy` only soft-archives companies). | **Remediated** in `privacy-policy/page.tsx` Sections 7, 9, 11, 13. |
| **F-05** | **P1** | `/pricing` Overclaimed Capabilities | Overclaimed live GST/E-Way/E-Invoice execution, full batch/serial & alternate-unit invoicing deduction, and generalized offline support across workflows. | **Remediated** in [`frontend/src/app/pricing/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/pricing/page.tsx). |
| **F-06** | **P1** | Missing Crawler / Indexing Controls | Missing `robots.txt` and `sitemap.xml` risked indexing `/share/[type]/[token]`, `/claim`, or internal app routes instead of focusing search engines on public pages. | **Remediated** via [`frontend/src/app/robots.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/robots.ts) & [`frontend/src/app/sitemap.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/sitemap.ts). |
| **F-07** | **P2** | Contact Form `mailto:` Bounds & Delivery Expectation | Needed input max lengths, control-character/CRLF sanitization, `<= 1900` URI cap warning, and unambiguous statement that SriLekh cannot guarantee delivery until sent by the user's email client. | **Remediated** in [`contact-validation.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/contact-validation.ts) & [`ContactForm.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/components/public/ContactForm.tsx). |
| **F-08** | **P2** | `/refund-policy` Pre-Launch Wording Ambiguity | Section 9 procedure could be misread as supporting live refund submissions today before online billing exists. | **Remediated** in [`refund-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/refund-policy/page.tsx). |
| **F-09** | **P2** | Out-of-Scope Client Token Architecture | `frontend/src/utils/auth.ts` stores JWT `access_token`/`refresh_token` in non-`HttpOnly` JS cookies and `localStorage`; `offlineDb.ts` logout `caches.delete` loop only checks `srilekh`/`vouch`/`pages` directly (relies on SW `CLEAR_SESSION_CACHES` for any legacy cache names). | **Documented (Out-of-Scope for Stage 1.1 Edit)** — tracked as backend/auth roadmap recommendation before GA security audit. |
| **F-10** | **P3** | SEO Metadata & Step 1 PDF Drift | Subpages (`/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`) inherit root `openGraph.title`/`description` from `layout.tsx`, `/` has no `canonical` tag and logged 1 `net::ERR_CONNECTION_REFUSED` in local Next-only preview, and `SriLekh_Public_Compliance_Pages.pdf` predates Stage 1.1 edits. | **Documented** in `STAGE_1_1_PUBLIC_ROUTE_QA.md`. |

---

## 3. Summary Matrix of Deliverables

1. [`STAGE_1_1_CAPABILITY_VERIFICATION_MATRIX.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_CAPABILITY_VERIFICATION_MATRIX.md) — Line-by-line backend/frontend/test evidence for Claims A–I.
2. [`STAGE_1_1_PRIVACY_DATA_FLOW_AUDIT.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_PRIVACY_DATA_FLOW_AUDIT.md) — Exact data collection, AI/processor flows, browser/IDB storage, tenant isolation, retention, and security control accuracy.
3. [`STAGE_1_1_DPDP_LEGAL_READINESS.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_DPDP_LEGAL_READINESS.md) — DPDP Act 2023 & DPDP Rules 2025 phased-commencement readiness assessment.
4. [`STAGE_1_1_CONTACT_AND_COMMERCIAL_REVIEW.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_CONTACT_AND_COMMERCIAL_REVIEW.md) — Contact dispatch safety, commercial/Razorpay/refund alignment.
5. [`STAGE_1_1_PUBLIC_ROUTE_QA.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_PUBLIC_ROUTE_QA.md) — Tests, TypeScript, ESLint, Next.js build, `sw.js` bundle audit, `robots.txt`/`sitemap.xml`, and Playwright (`msedge`) live DOM/responsive/accessibility checks.
6. [`STAGE_1_1_OWNER_CONFIRMATION_CHECKLIST.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_OWNER_CONFIRMATION_CHECKLIST.md) — 20-item checklist gating full public launch & payment gateway onboarding.

---

## 4. Stage 1.1 Release Classifications (Section 15)

| Dimension | Classification | Rationale |
| :--- | :--- | :--- |
| **1. Technical Implementation (Public Pages & SW Hygiene)** | **READY** | Targeted public pages, `ContactForm`, `robots.ts`, `sitemap.ts`, `sw-cache-policy.ts`, and `sw.ts` pass TypeScript (`tsc --noEmit`), scoped ESLint (`0` issues), 23/23 Node unit/sync tests, Next.js production build, and live Playwright (`msedge`) route QA. *(Pre-existing lint debt in unrelated ERP files and non-HttpOnly JWT design tracked separately.)* |
| **2. Factual Technical Accuracy** | **READY FOR OWNER/LEGAL REVIEW** | Overstated claims regarding batch/serial deduction, E-Way/E-Invoice/live GSTN filing, offline workflow scope, AI Gemini document transmission, shared-device outbox persistence, and deletion tooling have been aligned with verified codebase behavior. |
| **3. Privacy Engineering** | **CONDITIONAL (P0 Remediated; Core Token Hardening Deferred)** | Public-layer P0 Service Worker cross-origin cache risk is remediated and disclosures match code (`VouchOfflineDB`, `VouchSecurityVault`, `localStorage`, Gemini, Neon/Render/Vercel). Full production hardening recommends migrating away from JS-readable tokens to `HttpOnly` auth cookies + formal backup/account-erasure workflow. |
| **4. Legal Readiness (India DPDP & Terms/Refunds)** | **BLOCKED ON OWNER & COUNSEL INPUT** | Legal entity identity, registered address, Grievance Officer, jurisdiction city, processor DPAs, liability cap/indemnity wording, and statutory retention/deletion SLAs remain unfilled placeholders requiring owner + Indian counsel sign-off (note core Data Fiduciary duties under DPDP Rules, 2025 phase in by May 13, 2027). |
| **5. Commercial / Payment Gateway Readiness** | **BLOCKED ON OWNER DECISIONS & KYC** | Subscription INR plans, billing cycles, GST invoicing rules, refund windows, cancellation rules, verified support phone, and physical office address matching business KYC are not finalized; online checkout is correctly marked inactive. |
| **6. Publication Recommendation** | **HOLD FOR STAGING / PRE-PUBLICATION REVIEW ONLY** | Do **not** submit to Razorpay KYC or advertise publicly as final legal/commercial terms until the blocking items in [`STAGE_1_1_OWNER_CONFIRMATION_CHECKLIST.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_OWNER_CONFIRMATION_CHECKLIST.md) are supplied and Step 1 baseline PDF (`SriLekh_Public_Compliance_Pages.pdf`) is regenerated from the updated Stage 1.1 pages. |
