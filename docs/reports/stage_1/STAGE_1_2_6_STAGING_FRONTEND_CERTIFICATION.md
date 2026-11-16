# SRI LEKH — STAGE 1.2.6 STAGING FRONTEND ACCESS CERTIFICATION

**Assessment Date:** 2026-11-12  
**Feature Branch:** `feat/google-play-launch-readiness` @ `c160fca0` (repo HEAD `1a7abf64`)  
**Status (OA-09):** **BLOCKED (Owner Dashboard Action Required)**

---

## 1. Diagnostic Findings & Evidence

1. **DNS Probes for `staging.srilekh.com`:**
   - Command: `nslookup staging.srilekh.com 8.8.8.8`
   - Result: `*** 8.8.8.8 can't find staging.srilekh.com: Non-existent domain` (`NXDOMAIN`).
   - Impact: No DNS CNAME or A record has been created for `staging.srilekh.com` on GoDaddy nameservers (`ns21.domaincontrol.com` / `ns22.domaincontrol.com`).

2. **HTTP Probes for Vercel Preview Deployments:**
   - GitHub Deployments API returned Preview deployment ID `7743707294` (`1a7abf64`) -> `https://vouch-5h3qdcl3o-trail-blazer.vercel.app` and `7743272279` (`c160fca0`) -> `https://vouch-bhfez4lgk-trail-blazer.vercel.app`.
   - Live HTTP GET request (`allow_redirects=False`) to:
     - `https://vouch-5h3qdcl3o-trail-blazer.vercel.app` -> **`HTTP 302 Found`** -> `Location: https://vercel.com/sso-api?url=https%3A%2F%2Fvouch-5h3qdcl3o-trail-blazer.vercel.app%2F&nonce=...`
     - `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` -> **`HTTP 302 Found`** -> `Location: https://vercel.com/sso-api?...`
     - `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app` -> **`HTTP 302 Found`** -> `Location: https://vercel.com/sso-api?...`
   - Diagnosis: The Vercel project has **Deployment Protection (Vercel Authentication / SSO)** enabled for all preview deployments. Anonymous HTTP clients, automated headless test runners (Playwright), and external auditors receive an interactive Vercel OAuth login page.

3. **Inspection of Connected Production Deployments:**
   - Probed `https://vouch-pi-one.vercel.app`: Returns `HTTP 200` without SSO, but routes `/privacy-policy`, `/terms`, `/refund-policy`, `/contact`, `/pricing`, `/delete-account` return **`HTTP 404`** because this alias is bound to an older pre-Stage-1.1 commit and does NOT track `feat/google-play-launch-readiness`.

4. **Staging API & CORS Posture (`https://vouch-u3u7.onrender.com`):**
   - Staging backend API is online, healthy, and isolated (`commit: c160fca0`, `database: neondb_staging`, `migrations.unapplied_count: 0`).
   - CORS preflight (`OPTIONS /api/v1/auth/me/`) allows:
     - `Origin: https://vouch-pi-one.vercel.app` -> **ALLOWED**
     - `Origin: https://staging.srilekh.com` -> **ALLOWED**
     - `Origin: https://www.srilekh.com` -> **ALLOWED**
     - `Origin: https://evil.example.com` -> **REJECTED (`None`)**

---

## 2. Why the Automated Agent Cannot Bypass or Close OA-09 Autonomously

- `vercel` CLI is not installed on the workstation (`PATH_TOOLS['vercel'] == False`).
- No Vercel API token or personal access token exists in environment variables or GitHub secrets.
- No GoDaddy DNS API credentials exist to create the DNS record automatically.
- Bypassing or attempting to defeat an authentication gate (Vercel SSO) is strictly prohibited by behavioral guidelines.

---

## 3. Owner Action Instructions to Close OA-09 (2 Options)

### Option A (Recommended — 2-minute fix in Vercel Dashboard):
1. Log in to [vercel.com](https://vercel.com) and navigate to the **`vouch`** project.
2. Go to **Settings** -> **Deployment Protection**.
3. Under **Vercel Authentication**, toggle it to **Disabled** for Preview Deployments (or configure a **Protection Bypass for Automation** secret header `x-vercel-protection-bypass`).
4. Once disabled, `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app` will become immediately accessible to automated Playwright E2E and public preview.

### Option B (Custom Staging Domain):
1. In GoDaddy DNS Manager for `srilekh.com`, add a CNAME record:
   - **Type:** `CNAME`
   - **Name:** `staging`
   - **Value:** `cname.vercel-dns.com`
   - **TTL:** `1/2 Hour`
2. In Vercel Project Settings -> **Domains**, add `staging.srilekh.com` and assign it to the `feat/google-play-launch-readiness` or `fix/stage4-12-day6-remediation` branch.
3. Ensure `staging.srilekh.com` has Vercel Authentication disabled.

---

## 4. Prepared Playwright Staging E2E Suite

Once Option A or B is executed, the following automated E2E script is ready to run against the live deployed URL:

```bash
# Set deployed staging URL and run Playwright E2E against live Render backend
$env:PLAYWRIGHT_BASE_URL = "https://staging.srilekh.com"
npm --prefix frontend test -- src/e2e/staging_deployed.spec.ts
```

The test script exercises:
- Public pages: `/`, `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, `/delete-account`
- Cookie-based authentication & token erasure verification
- Idempotent sales voucher creation & offline outbox queueing
- Cloud reconciliation with live `vouch-u3u7.onrender.com`
- Multi-tab logout & tenant switching
