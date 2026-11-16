# SRI LEKH — STAGE 1.2.7 STAGING FRONTEND & E2E INTEGRATION CERTIFICATION

**Assessment Date:** 2026-11-12  
**Target Environments:**  
- Staging Web: `https://staging.srilekh.com` / Vercel Preview Deployments  
- Staging Backend API: `https://vouch-u3u7.onrender.com` (Commit `c160fca0`, `neondb_staging`)  
- Production Domain (Reference): `https://www.srilekh.com`  
**Certification Verdict:** **BLOCKED PENDING VERCEL SSO / DNS CNAME ACTION (OA-09)**  

---

## 1. Executive Summary

End-to-end integration testing between the staging frontend and the staging backend is required to certify that user authentication, offline voucher queueing, multi-tab logout, and financial reporting function properly in a deployed cloud environment.

In Stage 1.2.7, comprehensive live diagnostic probes were executed across all available Vercel deployment URLs, DNS records, and the staging backend API.

The local frontend build was verified:
- TypeScript compilation (`npx tsc --noEmit`): 0 errors.
- Unit and integration tests (`npm test`): 45/45 tests passed.
- Production bundle build (`npm run build`): All 57 static and dynamic routes compiled successfully with the Serwist offline service worker (`/sw.js`).

However, automated browser E2E testing against the live deployed staging frontend remains blocked because:
1. `staging.srilekh.com` returns `NXDOMAIN` on GoDaddy DNS.
2. Vercel preview deployment URLs return `HTTP 302` redirecting to `https://vercel.com/sso-api` (Vercel Preview Deployment Protection).

---

## 2. Live Diagnostic Probe Evidence

Probing script `scripts/probe_frontend_endpoints.py` evaluated public web targets:

| Target URL | Observed Response | Technical State |
| :--- | :--- | :--- |
| `https://staging.srilekh.com` | `URLError: [Errno 11001] getaddrinfo failed` | **NXDOMAIN**: CNAME not created on GoDaddy nameservers (`ns21/ns22.domaincontrol.com`). |
| `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` | `HTTP 302 -> https://vercel.com/sso-api?...` | **BLOCKED BY SSO**: Vercel Preview Deployment Protection redirects unauthenticated requests to Vercel team login. |
| `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app` | `HTTP 302 -> https://vercel.com/sso-api?...` | **BLOCKED BY SSO**: Preview deployment protection active. |
| `https://vouch-5h3qdcl3o-trail-blazer.vercel.app` | `HTTP 302 -> https://vercel.com/sso-api?...` | **BLOCKED BY SSO**: Preview deployment protection active. |
| `https://vouch-pi-one.vercel.app` | `HTTP 200` on `/` & `/login`; `HTTP 404` on `/privacy-policy`, `/terms`, `/contact`, `/pricing`, `/delete-account` | **OUTDATED MAIN BUILD**: Serving pre-Stage-1.1 commit before statutory routes were added. |
| `https://www.srilekh.com` | `HTTP 200` on `/` & `/login`; `HTTP 404` on `/privacy-policy`, `/terms`, `/contact`, `/pricing`, `/delete-account` | **OUTDATED PRODUCTION BUILD**: Serving pre-Stage-1.1 commit on `main`. |
| `https://vouch-u3u7.onrender.com/api/v1/health/environment/` | `HTTP 200` (healthy, `neondb_staging`, `6f4741bdaaf4`) | **HEALTHY & ISOLATED**: Staging backend is active and ready. |

---

## 3. Root Cause Analysis: Vercel Preview Protection

Vercel Pro accounts include a security feature named **Deployment Protection**:
- By default, Vercel enables "Vercel Authentication" for all non-production deployments (branches and pull requests).
- Any visitor or headless browser (Playwright, Puppeteer, curl) attempting to access a `.vercel.app` preview URL is redirected via `HTTP 302` to `https://vercel.com/sso-api` to authenticate with a Vercel team account.
- Because automated test runners cannot log into Vercel via SSO, public E2E probes are intercepted before reaching the Next.js application.

---

## 4. Step-by-Step Owner Action Runbook to Unblock Staging Frontend (OA-09)

The owner can resolve this blocker in **under 2 minutes** via either of the following two options:

### Option A: Disable Vercel Preview Deployment Protection (Fastest — 2 Minutes)
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

## 5. Automated E2E Test Suite Specification (Post-Unblock)

Once Option A or Option B is completed, the Playwright staging E2E suite will execute against the live URL:

```bash
cd frontend
NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com npx playwright test --config=playwright.staging.config.ts
```

### Passing Verification Criteria:
1. Public compliance pages (`/privacy-policy`, `/terms`, `/contact`, `/refund-policy`, `/delete-account`, `/pricing`) return `HTTP 200`.
2. Authentication flow using synthetic staging credentials (`Apex Belting Store` sandbox) issues `HttpOnly` session cookies.
3. Offline voucher creation in browser Service Worker outbox queues transactions and syncs upon reconnection without double-posting.
4. Multi-tab logout clears all session cookies across tabs.
5. Trial Balance and Balance Sheet views render with `0.00 INR` variance.
