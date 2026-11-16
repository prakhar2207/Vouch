# SRI LEKH — STAGE 1.2.1: OFFLINE & INTEGRATION VERIFICATION REPORT

**Verification Date:** 2026-11-12  
**Live Backend Verified:** `https://vouch-u3u7.onrender.com` (commit `f8578a88`, `neondb_staging`)  
**Scope:** Stage 4.15 API compatibility under cookie authentication, Stage 1.1 public route continuity, offline sync/privacy verification (`VouchOfflineDB`, `VouchSecurityVault`, `LogoutConfirmModal`, multi-tab coordination), and Capacitor boundary status.

---

## 1. Stage 4.15 Backend API Compatibility Under Cookie Auth (Live Staging)

Using a cookie-authenticated session (`srilekh_access`, `srilekh_refresh`, `X-CSRFToken`) on `Stage 4.14 Live Audit Sandbox` (`e09b235c-fffa-4410-a162-cb212fc4b3b6`) against `https://vouch-u3u7.onrender.com`:

| Stage 4.15 Workflow / Endpoint | Method & Auth Mode | Observed Response | Equilibrium / Integrity Check | Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/companies/` | Cookie-only | HTTP `200` | Tenant membership resolved cleanly under `CookieJWTAuthentication`. | **PASS** |
| `GET /api/v1/accounting/reports/balance-sheet/?company_id=e09b235c-...` (pre-write) | Cookie-only | HTTP `200` | `is_balanced: true`, `difference: "0.00"`. | **PASS** |
| `GET /api/v1/accounting/reports/balance-sheet/?company_id=cd788d07-...` (Garodia IDOR) | Cookie-only | HTTP `403` | Cross-tenant IDOR rejected cleanly under cookie auth. | **PASS** |
| `GET /api/v1/accounting/reports/trial-balance/e09b235c-.../` | Cookie-only | HTTP `200` | Accessible via HttpOnly cookie auth. | **PASS** |
| `GET /api/v1/accounting/reports/profit-and-loss/e09b235c-.../` | Cookie-only | HTTP `200` | Accessible via HttpOnly cookie auth. | **PASS** |
| `GET /api/v1/accounting/vouchers/?company_id=e09b235c-...` | Cookie-only | HTTP `200` | Voucher register read verified. | **PASS** |
| `GET /api/v1/ledgers/75017e43-.../statement/` (`X-Company-ID`) | Cookie-only | HTTP `200` | Ledger statement read verified. | **PASS** |
| `GET /api/v1/notifications/?company_id=e09b235c-...` | Cookie-only | HTTP `200` | Notification feed read verified. | **PASS** |
| `POST /api/v1/accounting/sales-invoice/` (`post_immediately: true`) + `GET /vouchers/detail/<id>/` + post-write Balance Sheet | Cookie + `X-CSRFToken` | `POST` HTTP `201` (`INV/26-27/0008`, `cc31b661-47ce-4746-afec-6ad570dabee9`); `GET` detail HTTP `200`; post-write Balance Sheet HTTP `200` | `is_balanced: true`, `difference: "0.00"` preserved after live invoice posting. | **PASS** |
| `scripts/test_live_render_staging.py --expected-commit f8578a88` | Baseline harness | Exited `0` (all probes) | `Precision Agro Tools Pvt Ltd` Assets Rs 1845954.26 == Liab Rs 1845954.26 (`Diff: Rs 0.00`), cross-tenant IDOR `403`. | **PASS** |

---

## 2. Offline Privacy, Outbox Isolation, Logout & PWA Verification

### A. Live Deployed Staging Frontend Browser Offline / Multi-Tab E2E
- **Status:** **BLOCKED**
- **Reason:** As documented in [`STAGE_1_2_1_STAGING_DEPLOYMENT_REPORT.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_2_1_STAGING_DEPLOYMENT_REPORT.md), no publicly accessible staging Next.js URL wired to `https://vouch-u3u7.onrender.com` was reachable (`staging.srilekh.com` DNS fails; `vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` is behind Vercel Deployment Protection SSO login and lacks preview CORS whitelisting on Render). Therefore, multi-tab live browser UI execution, real browser IndexedDB/SW cache inspection against staging Vercel, and live deployed `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy` HTTP rendering could **not** be executed on staging.

### B. Post-Commit Frontend Regression & Production Build Evidence (Local Node/Webpack)
Executed in `frontend/` cleanly against commit `f8578a88`:

| Check | Scope | Result | Notes |
| :--- | :--- | :--- | :--- |
| `npm test` (`frontend/`) | **28 / 28 passed** (`0 fail`, `0 skip`, `2.24s`, `exit 0`) | **PASS** | Covers Contact form (`6`), Service Worker cache policy (`3`), Stage 4.12 offline outbox (`5`), Stage 1.2 offline auth/privacy (`5`), Role capabilities (`4`), Auth utilities (`3`). Verifies zero JS JWTs in `localStorage`/`document.cookie`, User A vs User B & Company A vs B outbox isolation, `AbortController` in-flight sync discard on logout, and Secure Shared-Device wipe (`VouchOfflineDB`, `VouchSecurityVault`, `vouch_*`). |
| `npx tsc --noEmit` (`frontend/`) | Full TypeScript type-check | **PASS** (`0` errors, `exit 0`) | Executed immediately preceding `npm run build` in chained task (`task-12430`). |
| `npm run build` (`frontend/`) | Production Webpack + Serwist `/sw.js` build | **PASS** (`56/56` static pages, `exit 0`) | Cleanly generated `/sw.js`, `/robots.txt`, `/sitemap.xml`, `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/login`, `/register`, `/claim`, `/dashboard`. |

*(Prior Stage 1.2 local Edge E2E and Stage 1.1 local QA — performed before commit `f8578a88` — remain documented in [`STAGE_1_2_TARGETED_REGRESSION_RESULTS.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_2_TARGETED_REGRESSION_RESULTS.md) and [`STAGE_1_1_PUBLIC_ROUTE_QA.md`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/STAGE_1_1_PUBLIC_ROUTE_QA.md) and are kept strictly separate from live deployed staging checks.)*

---

## 3. Capacitor Mobile Boundary Verification Status

- **Backend API compatibility (`X-Client-Type: capacitor` on `https://vouch-u3u7.onrender.com`):** **PASS** (login `auth_mode=token` with JSON tokens, Bearer write without CSRF `200`, JSON refresh `200`, Bearer logout `200` -> `401` revocation).
- **Frontend Capacitor storage unit suite (`Mock Capacitor.Plugins.Preferences`):** **PASS** (verified inside `28/28` `npm test`).
- **Physical Android / iOS binary execution:** **NOT RUN** (no Android emulator/device or iOS simulator in workspace; not claimed as mobile device certification).
