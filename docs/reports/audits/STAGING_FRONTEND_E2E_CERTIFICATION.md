# SRI LEKH — STAGING & LOCAL FRONTEND E2E CERTIFICATION

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Modules Updated in Stage 1.2.3:** [`api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts), [`api.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.test.ts), [`privacy-policy/page.tsx`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/app/privacy-policy/page.tsx)

---

## 1. Environment Isolation & URL Guard Verification

Updated [`resolveApiBaseUrl`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts) so preview/staging web hosts (`*staging*`, `*preview*`, `*.vercel.app`, `*.onrender.com`) **never** silently fall back to `https://api.srilekh.com` when `NEXT_PUBLIC_API_URL` is omitted:
- Preview/staging hostnames without `NEXT_PUBLIC_API_URL` route safely to `https://vouch-u3u7.onrender.com`.
- Explicit staging contexts (`NEXT_PUBLIC_APP_ENV=staging` or staging hostnames) **fail closed** (`throw Error`) if configured with production API hosts (`api.srilekh.com`, `vouch-api-752s.onrender.com`).
- Official web domains (`srilekh.com`, `www.srilekh.com`, `app.srilekh.com`) and native Capacitor APK builds continue to resolve to `https://api.srilekh.com`.
- Verified **4 / 4** tests in [`api.test.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.test.ts) (`npm test` -> `39 / 39` pass).

---

## 2. Production Build & Playwright Chromium (`msedge`) Local E2E (`PASS`)

Executed against the rebuilt production Next.js `16.4.6` server (`next start -p 3000`, `57 / 57` static/dynamic routes + Serwist `/sw.js`) paired with an isolated local SQLite Django server (`http://127.0.0.1:8000`):
1. **Public & Auth Routes:** Verified `HTTP 200` and zero page errors across `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/login`, `/register`, and `/delete-account`.
2. **Privacy Disclosure Parity:** Verified `/privacy-policy` renders updated `AES-GCM` offline encryption disclosures and no stale `remain plaintext at rest` wording.
3. **Native Capacitor Commercial Guards:** Verified simulated Android Capacitor (`window.Capacitor.isNativePlatform() === true`) suppresses checkout/subscription CTAs on `/pricing` and `/refund-policy`.
4. **Cookie Auth, Zero DOM JWTs, Chromium WebCrypto IDB & Account Deletion:**
   - Verified `POST /api/v1/auth/login/` returns `200`, `auth_mode: "cookie"`, zero `access` JWT in JSON body, and zero `eyJ` strings in `localStorage`, `sessionStorage`, or `document.cookie`.
   - Verified Chromium WebCrypto generates and persists non-extractable (`extractable === false`) 256-bit `AES-GCM` keys into IndexedDB cleanly.
   - Verified `/api/v1/auth/account/delete-request/` returns `200`, immediately invalidates `/api/v1/auth/me/` (`401`), and exposes non-PII `/api/v1/auth/account/delete-status/` (`200`).

---

## 3. Deployed Staging Frontend E2E Status (`BLOCKED`)

- **Backend Live Telemetry (`https://vouch-u3u7.onrender.com`):** Verified live on `fix/stage4-12-day6-remediation` (`f8578a88`) with `neondb_staging` isolation (`6f4741bdaaf4`), security headers (`nosniff`, `DENY`, HSTS preload, `strict-origin-when-cross-origin`), `401` rejection on `/auth/me/`, `/accounting/vouchers/`, `/notifications/logs/`, and CORS rejection of untrusted origins. `/api/v1/auth/account/delete-request/` returns `404` on Render staging only because `feat/google-play-launch-readiness` is intentionally unpushed pending review.
- **Deployed Cross-Origin Staging Frontend E2E (`BLOCKED`):** Public `staging.srilekh.com` frontend deployment is still unavailable / gated without staging Render deployment of `feat/google-play-launch-readiness`. End-to-end deployed staging browser flows against Vercel staging + Render staging + live SMTP inbox remain **BLOCKED** until staging hosting is wired and approved.
