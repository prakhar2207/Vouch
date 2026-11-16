# SRI LEKH — STAGE 1.2.8 STAGING FRONTEND & E2E INTEGRATION CERTIFICATION

**Assessment Date:** 2026-11-13  
**Target Environments:**  
- Staging Web: `https://staging.srilekh.com` / Vercel Preview Deployments  
- Staging Backend API: `https://vouch-u3u7.onrender.com` (Commit `c160fca0`, `neondb_staging`)  
- Production Domain (Reference): `https://www.srilekh.com`  
**Certification Verdict:** **BLOCKED PENDING VERCEL SSO / DNS CNAME ACTION (OA-09)**  

---

## 1. Executive Summary

End-to-end integration testing between the deployed frontend and the staging backend is required to independently certify user session establishment, offline voucher queueing, multi-tab logout synchronization, and financial statement rendering in a realistic cloud environment.

In Stage 1.2.8, live diagnostic probes were re-executed across all public web targets:
- `https://staging.srilekh.com` -> `NXDOMAIN` (unmapped in GoDaddy DNS).
- Vercel preview deployment URLs (`https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app`, `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app`, etc.) -> `HTTP 302` redirecting to `https://vercel.com/sso-api` (Vercel Preview Deployment Protection SSO wall).
- `https://www.srilekh.com` and `https://vouch-pi-one.vercel.app` -> `HTTP 200` on `/` & `/login`, but `HTTP 404` on `/privacy-policy`, `/terms`, `/contact`, `/pricing`, `/delete-account` (serving pre-Stage-1.1 production commit).
- Staging backend API (`https://vouch-u3u7.onrender.com/api/v1/health/environment/`) -> Healthy, isolated to `neondb_staging` (`6f4741bdaaf4`), 0 unapplied migrations.

Locally, the frontend code is completely verified:
- TypeScript (`npx tsc --noEmit`): 0 errors.
- Unit and integration tests (`npm test`): 45/45 tests passed.
- Production build (`npm run build`): All 57 static and dynamic routes compiled cleanly.

Automated browser testing against the live deployed staging frontend requires a simple 2-minute dashboard action from the project owner.

---

## 2. Live Probe Telemetry Record

Live HTTP probe executed on 2026-11-13 via `scripts/probe_frontend_endpoints.py`:

```
https://staging.srilekh.com -> URLError: [Errno 11001] getaddrinfo failed
https://vouch-pi-one.vercel.app -> HTTP 200 (pre-Stage-1.1 main build)
https://vouch-5h3qdcl3o-trail-blazer.vercel.app -> HTTP 302 (Location: https://vercel.com/sso-api?url=https%3A%2F%2Fvouch-5h3qdcl3o-trail-blazer.vercel...)
https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app -> HTTP 302 (Location: https://vercel.com/sso-api?url=https%3A%2F%2Fvouch-git-fix-stage4-12-day6-remedi...)
https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app -> HTTP 302 (Location: https://vercel.com/sso-api?url=https%3A%2F%2Fvouch-git-feat-google-play-launch-r...)
https://vouch-trail-blazer.vercel.app -> HTTP 302 (Location: https://vercel.com/sso-api?url=https%3A%2F%2Fvouch-trail-blazer.vercel.app%2F&no...)
https://srilekh.com -> HTTP 308 (Location: https://www.srilekh.com/...)
https://www.srilekh.com -> HTTP 200 (pre-Stage-1.1 main build)
```

---

## 3. Root Cause: Vercel Preview Deployment Protection

In Vercel Pro team accounts (team `trail-blazer`), Vercel automatically activates "Vercel Authentication" (SSO Wall) on all non-production deployments.

When this protection is active:
- Any visitor or headless browser (Playwright, curl) attempting to access a `.vercel.app` preview branch deployment is intercepted and redirected via `HTTP 302` to `https://vercel.com/sso-api` to log into a Vercel team account.
- Because automated test agents cannot complete SSO logins, E2E tests cannot reach the Next.js application routes.

---

## 4. Step-by-Step Owner Action Runbook (OA-09)

The owner can resolve this blocker in **under 2 minutes** via either of the following two options:

### Option A: Disable Vercel Preview Protection (Fastest — 2 Minutes)
1. Log into your Vercel Dashboard at `https://vercel.com`.
2. Select the **`vouch`** project (team `trail-blazer`).
3. Click **Settings** -> **Deployment Protection**.
4. Under **Vercel Authentication**, toggle the switch from **Enabled** to **Disabled** (or select "Only protect production").
5. Save changes.
6. Once disabled, preview URLs (e.g. `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app`) become publicly accessible to automated browser test agents.

### Option B: Configure Custom Domain `staging.srilekh.com` in GoDaddy & Vercel
1. **In GoDaddy DNS Management (`srilekh.com`):**
   - Click **Add New Record**.
   - **Type:** `CNAME`
   - **Name:** `staging`
   - **Value:** `cname.vercel-dns.com`
   - **TTL:** `1/2 Hour` or default.
2. **In Vercel Project Settings (`vouch`):**
   - Go to **Settings** -> **Domains**.
   - Add `staging.srilekh.com`.
   - Set Git branch to `fix/stage4-12-day6-remediation` (or `feat/google-play-launch-readiness`).
   - Under Domain-level Protection, ensure public access is permitted.

---

## 5. Automated E2E Verification Plan (Post-Unblock)

Once Option A or Option B is completed, the Playwright staging E2E suite will execute against the live URL:

```bash
cd frontend
NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com npx playwright test --config=playwright.staging.config.ts
```

### Passing Verification Criteria for Closure:
1. Public compliance pages (`/privacy-policy`, `/terms`, `/contact`, `/refund-policy`, `/delete-account`, `/pricing`) return `HTTP 200`.
2. Authentication flow using synthetic staging credentials (`Apex Belting Store` sandbox) issues `HttpOnly` session cookies.
3. Offline voucher creation in browser Service Worker outbox queues transactions and syncs upon reconnection without double-posting.
4. Multi-tab logout clears all session cookies across tabs.
5. Trial Balance and Balance Sheet views render with `₹0.00` variance.
