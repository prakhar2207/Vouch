# SRI LEKH — STAGE 1.2.2: STAGING & FRONTEND E2E CERTIFICATION REPORT

**Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness` (derived from staging `fix/stage4-12-day6-remediation` @ `f8578a88`)  
**Scope:** Reconcile unresolved Stage 1.2.1 deployed staging frontend browser E2E blockers alongside newly built Next.js (`57/57`) local Playwright verification.

---

## 1. Live Deployed Staging Frontend Status (`BLOCKED` — External Infrastructure)

Live deployment probes confirm the Stage 1.2.1 external hosting blockers remain unresolved because they require DNS, Vercel team Dashboard, and Render Dashboard configuration outside repository/agent permissions (plus safety boundary preventing unauthorized staging branch overwrites or production merges):

| Blocker | Observed Evidence | Classification |
| :--- | :--- | :--- |
| **`staging.srilekh.com` DNS** | Domain lookup fails (`getaddrinfo failed`); no CNAME/A record points to Vercel staging. | **BLOCKED** (Owner DNS action) |
| **Vercel Branch Preview SSO Gate** | `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app/pricing` returns Vercel SSO login wall (`Title: Login – Vercel`, `X-Matched-Path: /login`), blocking headless browser E2E without Vercel SSO / Protection Bypass secret. | **BLOCKED** (Vercel Dashboard action) |
| **Preview CORS / CSRF / `NEXT_PUBLIC_API_URL`** | Live `OPTIONS https://vouch-u3u7.onrender.com/api/v1/auth/login/` for the preview origin returned `Access-Control-Allow-Origin: None` (Render `CORS_ALLOWED_ORIGINS` = `https://vouch-pi-one.vercel.app,https://staging.srilekh.com`). Without verified `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`, non-localhost builds fall back to production `https://api.srilekh.com` per [`frontend/src/utils/api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts). | **BLOCKED** (Render + Vercel Env setup) |
| **Production Domains (`srilekh.com` / `vouch-pi-one.vercel.app`)** | Track `main` (returned `404` on `/pricing`); strictly excluded from staging testing. | **PROTECTED** |

**Exact Prerequisites to Unblock Deployed Browser E2E:**
1. Point `staging.srilekh.com` (or disable Vercel Deployment Protection on staging preview / supply `x-vercel-protection-bypass` header) to a staging Vercel deployment built with `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`.
2. Ensure Render `vouch-u3u7` `CORS_ALLOWED_ORIGINS` & `CSRF_TRUSTED_ORIGINS` include that exact staging frontend origin (already allows `https://staging.srilekh.com` cleanly once DNS points there).
3. Merge/push `feat/google-play-launch-readiness` to staging branch after review and run the 20-step deployed Playwright E2E test suite against `staging.srilekh.com`.

---

## 2. Live Deployed Staging Backend & API E2E Status (`Verified PASS` from Stage 1.2.1 on `f8578a88`)

Re-confirmed live on `https://vouch-u3u7.onrender.com` (`commit: f8578a88`, `neondb_staging`, fingerprint `6f4741bdaaf4`):
- `GET /api/v1/health/environment/` -> `200`, `"migrations": {"status": "up_to_date", "unapplied_count": 0}`, `is_isolated: true`.
- Security response headers observed live: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Browser cookie login (`X-Client-Type: web`, `HttpOnly; Secure; SameSite=None`), CSRF `403/200` enforcement (`PATCH`/`POST`/`DELETE`), refresh rotation + replay `401`, logout cookie clear + `token_version` bump -> `401`, CORS origin checks, Capacitor Bearer flow, and Stage 4.15 cookie-auth accounting parity all **Verified PASS** against `f8578a88`.

---

## 3. Post-Change Local Production Build & Browser E2E Evidence (`Verified PASS` — NOT Substituted for Live Deployed Staging)

Executed cleanly on `feat/google-play-launch-readiness` against newly built Next.js (`57/57` static pages + Serwist `/sw.js`) and isolated local Django SQLite:

| Local Verification Item | Executed Scope | Observed Result | Distinction |
| :--- | :--- | :--- | :--- |
| **`npm test` (`frontend/`)** | `28 / 28` tests across 4 suites (Contact validation, SW cache isolation, Stage 4.12 offline sync, Stage 1.2 offline auth/privacy, Role/Auth utils) | **Verified PASS** (`28/28`, `0` fail, `0` skip) | Local unit/IndexedDB tests (`fake-indexeddb` + mocks) |
| **`npx tsc --noEmit` & `npm run build`** | TypeScript type-check (`0` errors) + Webpack production build (`57/57` routes + `/sw.js`) | **Verified PASS** (`exit 0`) | Local production bundle check |
| **Playwright (`msedge`) Local E2E (`verify_play_launch_browser_e2e.py`)** | Web mobile viewport (`390x844`): all 9 public routes (`200`), `robots.txt` & `sitemap.xml` include `/delete-account`, `/privacy-policy` updated; Simulated Capacitor native guard (`res=True`): `/pricing` & `/refund-policy` blocked, footer hides Pricing/Refund; Authenticated `/login?next=/delete-account` -> permanent account deletion `COMPLETED` receipt + zero `eyJ` in DOM. | **Verified PASS** (`exit 0`) | Same-site local build (`localhost:3000` <-> `localhost:8000`); live cross-origin Vercel <-> Render still **BLOCKED** |
| **Multi-Tab UI Logout, Offline Mode UI & Reconnection Sync on Deployed Staging Frontend** | Requires accessible deployed `staging.srilekh.com` wired to `vouch-u3u7.onrender.com`. | **BLOCKED** *(Unit & Stage 1.2 local Edge E2E covered logic separately)* | Pending staging DNS/Vercel bypass |
