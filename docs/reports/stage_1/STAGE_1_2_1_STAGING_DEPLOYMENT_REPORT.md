# SRI LEKH — STAGE 1.2.1: STAGING DEPLOYMENT REPORT

**Verification Date:** 2026-11-12  
**Branch:** `fix/stage4-12-day6-remediation`  
**Deployed Commit SHA:** `f8578a88254f5d36f3cb3c5a1feed56f31ca1afe` (short: `f8578a88`)  
**Previous Staging Commit SHA:** `016f7948`  

---

## 1. Environment & Isolation Summary (Zero Production Impact Proof)

| Component | Target Observed | Isolation / Safety Proof | Status |
| :--- | :--- | :--- | :--- |
| **Staging Backend Service** | `https://vouch-u3u7.onrender.com` | `/api/v1/health/environment/` returned `"environment": "staging"`, `"commit": "f8578a88"`, `"version": "1.0.2"`. | **PASS** |
| **Staging Database** | PostgreSQL `neondb_staging` (`ep-silent-feather-b34egg28-pooler.c-4.ap-southeast-1.aws.neon.tech`) | `identity_fingerprint: "6f4741bdaaf4"`, `"is_isolated": true`; `scripts/verify_staging_identity.py` verified `Target Database: neondb_staging`, `Production Tenant in Staging: 0`, `Applied Migrations Count: 146`. | **PASS** |
| **Production Backend (`vouch-api-752s.onrender.com`)** | Untouched | Not deployed to, queried, or migrated. `main` and `release/stage4-final-rc-integration` untouched. | **PROTECTED** |
| **Production Tenant (`Maa Annapurna Belting Store`, `5d2e5dea-ff86-4871-b2af-fe1c5a05c03c`)** | 0 rows in `neondb_staging` | Asserted `0` rows prior to every write operation via [`verify_staging_identity.py`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/scripts/verify_staging_identity.py) and live certification harness. | **PROTECTED** |
| **Staging Frontend (`staging.srilekh.com` / Vercel Preview)** | `https://staging.srilekh.com` (no DNS); `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` (Vercel SSO protected) | External hosting blocker; `vouch-pi-one.vercel.app` and `srilekh.com` remain on `main` (returned `404` for `/pricing`) and were never used for staging auth tests. | **BLOCKED** |

---

## 2. Deployment & Database Migration Verification

1. **Git Commit & Branch Push:**
   - Staged and committed the 69 Stage 1.1 and Stage 1.2 code/report files cleanly onto `fix/stage4-12-day6-remediation` as commit `f8578a88254f5d36f3cb3c5a1feed56f31ca1afe`.
   - Pushed to `origin/fix/stage4-12-day6-remediation`, triggering Render's branch build (`./build.sh`: `pip install`, `collectstatic`, `python manage.py migrate`).
2. **Post-Deploy Render Health Check (`GET https://vouch-u3u7.onrender.com/api/v1/health/environment/`):**
   - Verified pre-test and post-test (`HTTP 200`):
     - `"status": "healthy"`
     - `"environment": "staging"`
     - `"commit": "f8578a88"`
     - `"database": {"engine": "postgresql", "sanitized_target": "neondb_staging", "identity_fingerprint": "6f4741bdaaf4", "is_isolated": true}`
     - `"migrations": {"status": "up_to_date", "unapplied_count": 0}`
   - Unchanged Stage 4.15 external infra blockers remain reported accurately as `"redis": {"configured": true, "status": "unreachable"}` and `"celery": {..., "workers_online": 0, "beat_schedule_active": false}`.
3. **Database Schema & Backfill Proof (`neondb_staging`):**
   - `python manage.py showmigrations accounts` (against `neondb_staging`): `[X] 0007_user_token_version` (`[X]` across `0001` through `0007`).
   - `python manage.py makemigrations --check --dry-run`: `No changes detected` (`exit 0`).
   - Direct `information_schema.columns` inspection: `accounts_user.token_version` present as `integer`, `is_nullable = 'NO'`.
   - User backfill check across all 12 synthetic staging accounts in `neondb_staging`: `(count=12, min(token_version)=0, max(token_version)=0)`.
   - `scripts/test_live_render_staging.py --base-url https://vouch-u3u7.onrender.com --expected-commit f8578a88`: all 4 probes + CORS preflight exited `0` (verified `Precision Agro Tools Pvt Ltd` Balance Sheet equilibrium `Diff: Rs 0.00` and `403` on cross-tenant IDOR).

---

## 3. Staging Frontend Deployment Gap & Exact External Blockers

Probes during deployment certification established three concrete external blockers preventing live browser E2E testing against a deployed staging frontend:

1. **Missing Custom Staging Domain DNS:** `GET https://staging.srilekh.com` fails DNS resolution (`getaddrinfo failed`).
2. **Vercel Preview Deployment Protection Gate:** GitHub check-runs confirm Vercel built commit `f8578a88` at `https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app`, which responds `HTTP 200` with Vercel's authentication wall (`<title>Login – Vercel</title>`, `X-Matched-Path: /login`) rather than SriLekh pages; no Vercel CLI, API token, or Deployment Protection bypass secret exists in this environment.
3. **Preview Origin CORS & API URL Mismatch:**
   - Live `OPTIONS https://vouch-u3u7.onrender.com/api/v1/auth/login/` with `Origin: https://vouch-git-fix-stage4-12-day6-remediation-trail-blazer.vercel.app` returned `Access-Control-Allow-Origin: None` because Render staging's `CORS_ALLOWED_ORIGINS` is explicitly configured as `https://vouch-pi-one.vercel.app,https://staging.srilekh.com` (and `CSRF_TRUSTED_ORIGINS` similarly omits arbitrary branch preview slugs).
   - As implemented in [`frontend/src/utils/api.ts`](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/frontend/src/utils/api.ts), non-localhost browser builds require `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`; without verifying Vercel Preview env vars, a preview frontend defaults to `https://api.srilekh.com`.

**Prerequisite to Unblock Staging Browser E2E:** Either provision `staging.srilekh.com` CNAME pointing to a public Vercel staging deployment with `NEXT_PUBLIC_API_URL=https://vouch-u3u7.onrender.com`, or disable Vercel SSO protection / provide a bypass token AND add the staging frontend origin to Render `CORS_ALLOWED_ORIGINS` + `CSRF_TRUSTED_ORIGINS`.

---

## 4. Synthetic Data Hygiene

- All live certification writes targeted only disposable ephemeral accounts (`cert_s121_*@staging.srilekh.internal`) attached strictly to existing sandbox tenant **`Stage 4.14 Live Audit Sandbox` (`e09b235c-fffa-4410-a162-cb212fc4b3b6`)**.
- After verification, `cert_s121_rst_*` was deleted cleanly and `cert_s121_*` was removed from `UserCompany` memberships and deactivated (`is_active=False`, retained only due to `Voucher.created_by` `PROTECT` FK integrity on synthetic `INV/26-27/0008`).
- Existing pilot cohort accounts (`owner_msme-plt-01`, `Garodia`, `Shree Radhe`) were read-only probed (Balance Sheet / IDOR) without credential or voucher mutations.
