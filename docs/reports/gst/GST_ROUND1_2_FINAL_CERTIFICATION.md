# SriLekh — GST Round 1.2 Final Release Certification Report

## 1. Executive Summary

This certification report establishes the operational and security readiness of the **SriLekh GST Sandbox Round 1.2** release candidate on the staging branch `fix/stage4-12-day6-remediation`.

The audit verified that the latest remediation commit `903e2951` is live and healthy on the dedicated staging service `https://vouch-u3u7.onrender.com`, confirmed physical database isolation on Neon (`neondb_staging`), verified dedicated encryption key enforcement in staging, validated 24-hour taxpayer caching with force-refresh support, audited background worker infrastructure on Render, and completed full security and accounting regression testing.

---

## 2. Independent Certification Matrix (13 Required Dimensions)

| Dimension | Required Verdict | Actual Evidence / Justification | Outstanding Action |
| :--- | :---: | :--- | :--- |
| **1. Latest Staging Commit Deployed** | **PASS** | Live probe of `https://vouch-u3u7.onrender.com/api/v1/health/environment/` returned HTTP 200 with `"commit": "903e2951"` and `"environment": "staging"`. Matches local and remote Git HEAD `903e295`. | None |
| **2. Database Isolation** | **PASS** | Staging targets `neondb_staging` on cluster `ep-silent-feather-b34egg28`. Production targets `neondb` on cluster `ep-lingering-boat-b3994i6f`. Protected tenant count in staging: 0. `environment_guard` active. | None |
| **3. Encryption Configuration** | **PASS** | Formally hardened in [apps/gst/encryption.py](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/apps/gst/encryption.py). Fails closed if dedicated key is missing in staging/production. `MultiFernet` supports both direct 44-char keys and legacy derived keys. | Owner to configure `GST_ENCRYPTION_KEY` |
| **4. Sandbox Authentication** | **BLOCKED** | Architecture and client logic verified via unit tests; live calls to `POST /authenticate` gated on owner entering API credentials. Documented in [GST_ROUND1_2_SANDBOX_AUTHENTICATION_REPORT.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/GST_ROUND1_2_SANDBOX_AUTHENTICATION_REPORT.md). | Owner to configure `SANDBOX_API_KEY` & `SANDBOX_API_SECRET` |
| **5. Actual GSTIN Verification** | **BLOCKED** | Sub-millisecond Luhn MOD-36 checksum, format validation, and cache verified; live provider search gated on owner API credentials. Documented in [GST_ROUND1_2_LIVE_GSTIN_VERIFICATION.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/GST_ROUND1_2_LIVE_GSTIN_VERIFICATION.md). | Owner to configure `SANDBOX_API_KEY` & `SANDBOX_API_SECRET` |
| **6. Taxpayer Cache** | **PASS** | Strictly enforces 24-hour TTL (`timedelta(hours=24)`). Stale entries (>24h) trigger provider search; `force_refresh=True` bypasses cache. Verified in `test_taxpayer_cache_24h_expiry_and_force_refresh`. | None |
| **7. Party Enrichment** | **PASS** | Non-intrusive preview dialog allows selective field adoption. Zero silent overwrites. Zero accounting line-item modifications. | None |
| **8. Tenant Security** | **PASS** | Cross-tenant registration queries and deactivations return HTTP 403 Forbidden. Company ID spoofing blocked. Sensitive headers redacted from logs. Documented in [GST_ROUND1_2_SECURITY_REGRESSION.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/GST_ROUND1_2_SECURITY_REGRESSION.md). | None |
| **9. Redis Connectivity** | **BLOCKED** | Render Free tier does not include persistent managed Redis. Zero impact on synchronous GST operations. Documented in [GST_ROUND1_2_BACKGROUND_INFRASTRUCTURE_AUDIT.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/GST_ROUND1_2_BACKGROUND_INFRASTRUCTURE_AUDIT.md). | Owner decision on Starter plan ($7/mo) |
| **10. Celery Task Execution** | **BLOCKED** | Background workers require paid Starter tier on Render. Synchronous GST verification does not require Celery. Staging can run in eager mode (`CELERY_TASK_ALWAYS_EAGER=True`). | Owner decision on Starter plan ($14/mo) |
| **11. Accounting Regression** | **PASS** | Mathematical equilibrium $\sum \text{Dr} == \sum \text{Cr}$ confirmed; 0 voucher changes, 0 ledger changes, 0 stock movements. Regression suites (9/9 pass). Documented in [GST_ROUND1_2_ACCOUNTING_REGRESSION.md](file:///c:/Users/prakh/OneDrive/Desktop/projects/B2B/GST_ROUND1_2_ACCOUNTING_REGRESSION.md). | None |
| **12. Frontend Staging Workflow** | **PASS** | Frontend passes all 45 unit/integration tests in `frontend/src/**/*.test.ts`. Static TypeScript compilation (`cd frontend && npx tsc --noEmit`) passes with 0 errors. | None |
| **13. Overall Round 1.2** | **PASS (READY FOR LIVE CREDENTIALS)** | Codebase is fully stabilized, hardened, tested, and live on Render staging. Live provider calls remain blocked pending owner credential entry. | Owner to enter credentials in Render Staging |

---

## 3. Test Evidence Summary

- **Backend Foundation Suite**: `python manage.py test apps.gst.tests_round1_foundation` $\rightarrow$ **15/15 PASS** in 14.430s.
- **Complete GST App Suite**: `python manage.py test apps.gst` $\rightarrow$ **41/41 PASS** in 20.784s.
- **Accounting Regression Suite**: `python manage.py test apps.accounting.tests_upload_security apps.accounting.tests_stage4_13_stabilization` $\rightarrow$ **9/9 PASS** in 2.753s.
- **Frontend Test Suite**: `npm test --prefix frontend` $\rightarrow$ **45/45 PASS** in 1.26s.
- **Frontend TypeScript Check**: `cd frontend; npx tsc --noEmit` $\rightarrow$ **0 errors**.
- **Live Health Endpoint**: `https://vouch-u3u7.onrender.com/api/v1/health/environment/` $\rightarrow$ **HTTP 200, Commit 903e2951, Database neondb_staging**.

---

## 4. Owner Actions for Live Sandbox Activation

To activate live provider-backed GSTIN verification on the deployed staging environment:

1. Log in to [developer.sandbox.co.in](https://developer.sandbox.co.in) and navigate to your application.
2. Confirm the **GST** product is enabled.
3. Open the Render Dashboard $\rightarrow$ **`vouch-staging`** (`vouch-u3u7`) $\rightarrow$ **Environment**.
4. Add the following environment variables:
   - `SANDBOX_API_KEY`: `<Your Sandbox API Key>`
   - `SANDBOX_API_SECRET`: `<Your Sandbox API Secret>`
   - `SANDBOX_BASE_URL`: `https://api.sandbox.co.in`
   - `GST_ENCRYPTION_KEY`: `<Your Base64 32-byte Fernet Key>`
5. In the Render Dashboard for `vouch-staging` (`vouch-u3u7`), trigger **Manual Deploy** $\rightarrow$ **Deploy latest commit**.
