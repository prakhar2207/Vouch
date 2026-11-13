# SRI LEKH — STAGE 1.2.5 PUBLIC WEBSITE & COMPLIANCE CERTIFICATION

**Assessment Date:** 2026-11-12  
**Evaluated Branch / Commit:** `feat/google-play-launch-readiness` @ `c160fca0`  
**Live Production Domain Probed:** `https://www.srilekh.com` (`main` untouched per production safety mandate)  
**Overall Gate Verdict (Gate A — Public Web Half):** **BLOCKED** *(Code & build ready on branch `feat/google-play-launch-readiness`; live `https://www.srilekh.com` still serves pre-branch `main` and returns `HTTP 404` on all 6 compliance/pricing/account-deletion URLs)*

---

## 1. Live Production Domain HTTP Probes (`2026-11-12`)

| Route | Expected Route on `feat/google-play-launch-readiness` | Live `https://www.srilekh.com` HTTP Status | Status |
| :--- | :--- | :--- | :--- |
| `/` | Public SaaS landing page | `200 OK` | **LIVE** |
| `/pricing` | Plan tiers & commercial disclosures | `404 Not Found` | **BLOCKED ON PRODUCTION** |
| `/contact` | Support contact & mailto handoff | `404 Not Found` | **BLOCKED ON PRODUCTION** |
| `/privacy-policy` | Updated SriLekh privacy & data-safety notice | `404 Not Found` | **BLOCKED ON PRODUCTION** |
| `/terms` | SaaS terms of service | `404 Not Found` | **BLOCKED ON PRODUCTION** |
| `/refund-policy` | Cancellation & refund policy | `404 Not Found` | **BLOCKED ON PRODUCTION** |
| `/delete-account` | Google Play self-service account deletion portal | `404 Not Found` | **BLOCKED ON PRODUCTION** |

---

## 2. Deployed Vercel Preview & DNS Observations

- **DNS Resolution (`nslookup`, GoDaddy `ns21.domaincontrol.com` / `ns22.domaincontrol.com`):**
  - `www.srilekh.com` -> `CNAME 6258a10bc7e3c111.vercel-dns-017.com`
  - `api.srilekh.com` -> `CNAME vouch-api-752s.onrender.com`
  - `staging.srilekh.com` -> **`Non-existent domain`** (`NXDOMAIN` — not provisioned)
- **Vercel Preview Deployment Status:**
  - GitHub commit statuses show Vercel auto-built `7c27c807` (`success`, `https://vercel.com/trail-blazer/vouch/G3QjFaXZDtco44bZrEWo5b41HVnQ`) and `c160fca0` (`success`, `https://vercel.com/trail-blazer/vouch/574S36ykQyKAquzLPPA9DRcz5dEK`).
  - Live GET on `https://vouch-git-feat-google-play-launch-readiness-trail-blazer.vercel.app/` (`allow_redirects=False`) returned **`HTTP 302`** -> `https://vercel.com/sso-api?...` (Vercel Deployment Protection / SSO Login Wall enabled). Anonymous crawlers, Play reviewers, and Playwright E2E cannot reach `.vercel.app` preview URLs without an owner-supplied bypass token or unauthenticated custom domain `staging.srilekh.com`.

---

## 3. Built Frontend Verification (Stage 1.2.4 & Post-Edit Stage 1.2.5)

- **Stage 1.2.4 Next.js Production Build & Browser E2E:** Built `57/57` routes cleanly (`Next.js 16.4.6` + Serwist `/sw.js`), passed Playwright Chromium (`msedge`) checks at `1440x900` and `390x844` (`HTTP 200`, `0px` horizontal overflow, zero `eyJ` token exposure), and verified `/delete-account` end-to-end against isolated backend.
- **Stage 1.2.5 CI Staging Bundle & Unit Suite (`43259891989` on `c160fca0` + local `cd frontend && npm test`):**
  - `npx tsc --noEmit`: **PASS** (`exit 0`)
  - `npm test`: **45 / 45 PASS** (`6` suites, `0` skipped, including `Contact form validation & mailto handoff` and `Service Worker Cache Policy & Session Isolation`)
  - `npm audit --omit=dev`: **`0` vulnerabilities**
  - `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com npm run build`: **PASS**

---

## 4. Remaining Actions Before Production Certification

1. **Owner Approval & Merge to `main` (`OA-01`):** Approve merging `feat/google-play-launch-readiness` into `main` so Vercel deploys `/pricing`, `/contact`, `/privacy-policy`, `/terms`, `/refund-policy`, and `/delete-account` live on `https://www.srilekh.com` (`HTTP 200`).
2. **Owner Legal Entity Confirmation (`OA-02`):** Replace `[Pending Owner Confirmation]` placeholders in public legal/contact pages (registered legal entity name, registered address, Grievance Officer name/contact, GSTIN/CIN if applicable, formal statutory accounting retention period in years).
3. **Staging Domain / Vercel SSO Wall (`OA-09`):** Bind `staging.srilekh.com` in GoDaddy + Vercel Dashboard pointing to staging preview or disable Vercel Preview SSO Protection before executing deployed staging frontend E2E.
