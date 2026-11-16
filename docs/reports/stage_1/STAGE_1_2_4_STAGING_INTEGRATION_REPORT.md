# SRI LEKH — STAGE 1.2.4 STAGING INTEGRATION REPORT

**Assessment Date:** 2026-11-12  
**Branch:** `feat/google-play-launch-readiness`  
**Overall Staging Gate Status (Gate D):** **BLOCKED** *(Local Build, Neon PG Integration, Live Staging Security Headers & CORS Verified; Deployed Staging Frontend & Feature Branch Rollout Pending)*

---

## 1. Live DNS & Deployment Telemetry

| Target | Observed Check Result | Detail / Status |
| :--- | :--- | :--- |
| **`https://vouch-u3u7.onrender.com/api/v1/health/environment/`** | **`HTTP 200`** | `environment: "staging"`, `version: "1.0.2"`, `commit: "f8578a88"`, `sanitized_target: "neondb_staging"`, `identity_fingerprint: "6f4741bdaaf4"`, `is_isolated: true`, `migrations.unapplied_count: 0`, `redis.status: "unreachable"`, `celery.workers_online: 0` |
| **Staging CORS `OPTIONS` (`vouch-u3u7.onrender.com/api/v1/auth/login/`)** | **`HTTP 200`** | `Origin: https://vouch-pi-one.vercel.app` -> `acao: https://vouch-pi-one.vercel.app, acac: true`; `Origin: https://staging.srilekh.com` -> `acao: https://staging.srilekh.com, acac: true`; `Origin: https://evil.example.com` -> `acao: None, acac: None` |
| **Staging Account Deletion Endpoint (`vouch-u3u7.onrender.com/api/v1/auth/account/delete-request/`)** | **`HTTP 404`** | Feature branch `feat/google-play-launch-readiness` is intentionally unpushed while awaiting owner approval; Render staging still runs `f8578a88` |
| **DNS `staging.srilekh.com`** | **`FAIL` (`getaddrinfo failed`)** | Staging custom domain has no live DNS record yet |
| **Live Public Web (`https://www.srilekh.com/`)** | **`HTTP 200` `/` ; `HTTP 404` on 6 compliance pages** | `/` serves `200` on Vercel (`x-frame-options: DENY`, `x-content-type-options: nosniff`, `strict-transport-security: max-age=63072000`, CSP `frame-ancestors 'none'`). `/privacy-policy`, `/terms`, `/refund-policy`, `/contact`, `/delete-account`, and `/pricing` all return **`HTTP 404`** |
| **Host Vercel / Render / GitHub CLIs** | **`MISSING`** | `vercel`, `render`, and `gh` CLIs are absent on this Windows workstation |

---

## 2. Local Built Frontend + Backend E2E Integration Verification (`PASS`)

Executed Playwright Chromium (`msedge`) E2E against `next start -p 3000` (production webpack bundle of `feat/google-play-launch-readiness`, `57/57` routes + Serwist `/sw.js`) paired with an isolated disposable SQLite Django server (`http://localhost:8000`) and Neon PostgreSQL `test_neondb_staging`:

- **Desktop (`1440x900`) & Mobile (`390x844`) Public/Auth Routes:** All 7 tested routes (`/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/delete-account`) returned **`HTTP 200`**, **`0px` horizontal overflow**, **`0` uncaught `pageerror`s**, and **`0` leaked `eyJ` JWT strings**.
- **Cross-Origin CSRF Rejection Observed Live in Browser:** Initial test run on untrusted port `:3124` was rejected by Django with **`HTTP 403` (`CSRF Failed: Origin checking failed - http://localhost:3124 does not match any trusted origins`)** before switching to configured `:3000`, proving active origin enforcement.
- **Full End-to-End Cookie Login -> WebCrypto -> Account Deletion:**
  - `POST /api/v1/auth/login/` set `HttpOnly` `srilekh_access` cookie (`httpOnly: true`); browser `localStorage`, `sessionStorage`, and `document.cookie` held **`0` JWTs**.
  - Chromium `window.crypto.subtle` confirmed non-extractable `AES-GCM-256` key (`webCryptoKeyNonExtractable: true`).
  - `/delete-account` flow executed cleanly (`POST /api/v1/auth/account/delete-request/` -> `200 COMPLETED`, non-PII status check `publicStatusZeroPii: true`).

---

## 3. Blockers Keeping Gate D **BLOCKED**

1. `feat/google-play-launch-readiness` is not pushed/deployed to Render staging (`vouch-u3u7.onrender.com` remains on `f8578a88`) or Vercel staging (`staging.srilekh.com` DNS missing).
2. Deployed cross-origin multi-tab browser E2E (Vercel staging <-> Render staging <-> live SMTP inbox) could not execute without live deployment & SMTP credentials.
