# SriLekh — GST Round 1.1 Final Release Certification Report

## 1. Executive Summary

This certification report establishes the operational and security readiness of the **SriLekh GST Sandbox Round 1.1** release candidate on the staging branch `fix/stage4-12-day6-remediation`.

The independent audit investigated the Render staging deployment failure, verified physical database isolation on Neon, audited the Fernet credential encryption architecture, re-tested all security and accounting invariants, and confirmed live deployment on `https://vouch-u3u7.onrender.com`.

---

## 2. Independent Certification Matrix (13 Required Dimensions)

| Dimension | Verdict | Evidence / Justification | Outstanding Action |
| :--- | :---: | :--- | :--- |
| **1. Round 1 Code Audit** | **PASS** | Inspected all 10 architectural invariants. Remediated 24h cache TTL, environment variable prefixes, and encryption descriptions. All tests pass. | None |
| **2. Render Deployment** | **PASS** | Live probe of `https://vouch-u3u7.onrender.com/api/v1/health/environment/` returns HTTP 200, `"commit": "8adc8da2"`, `"environment": "staging"`. Production service `vouch-api` safely protected from accidental staging deploy. | Owner to verify branch settings in Render dashboard |
| **3. Database Isolation** | **PASS** | Staging targets `neondb_staging` on cluster `ep-silent-feather-b34egg28`. Production targets `neondb` on cluster `ep-lingering-boat-b3994i6f`. Zero cross-tenant data. `environment_guard` active. | None |
| **4. Migration Verification** | **PASS** | Migration `gst.0006` adds nullable / defaulted fields to `gst_gstregistration`. Verified applied on `neondb_staging` (`unapplied_count: 0`). Zero accounting tables touched. | None |
| **5. Encryption Review** | **PASS** | Formally corrected documentation and field descriptor to Fernet Authenticated Envelope Encryption (AES-128-CBC + HMAC-SHA256). Fail-closed error handling verified. | None |
| **6. Provider Authentication** | **BLOCKED** | Architecture and client logic verified via unit tests; live calls to `POST /authenticate` gated on owner entering API credentials. | Owner to provide `SANDBOX_API_KEY` & `SANDBOX_API_SECRET` |
| **7. Actual GSTIN Verification** | **BLOCKED** | Sub-millisecond Luhn MOD-36 checksum, format validation, and cache verified; live provider search gated on owner API credentials. | Owner to provide `SANDBOX_API_KEY` & `SANDBOX_API_SECRET` |
| **8. Multi-GSTIN Workflow** | **PASS** | Multi-state registrations supported with atomic primary registration exclusivity and soft-deactivation. 12/12 foundation tests pass. | None |
| **9. Party Enrichment** | **PASS** | Non-intrusive preview dialog allows selective field adoption. Zero silent overwrites. Zero accounting line-item modifications. | None |
| **10. Tenant Isolation** | **PASS** | Cross-tenant registration queries and deactivations return HTTP 403 Forbidden. Company ID spoofing blocked. | None |
| **11. Accounting Integrity** | **PASS** | Mathematical equilibrium $\sum \text{Dr} == \sum \text{Cr}$ confirmed; 0 voucher changes, 0 ledger changes, 0 stock movements. Regression suites (9/9 pass). | None |
| **12. Frontend Staging Validation** | **PASS** | Frontend builds cleanly (`npx tsc --noEmit` $\rightarrow$ 0 errors); 45 unit/integration tests pass in `frontend/src/**/*.test.ts`. | None |
| **13. Overall Round 1.1** | **PASS (READY FOR STAGING TESTING)** | Codebase is fully stabilized, hardened, tested, and live on Render staging. Live provider calls remain blocked pending owner credential entry. | Owner to enter credentials in Render Staging |

---

## 3. Test Evidence Summary

- **Backend Foundation Suite**: `python manage.py test apps.gst.tests_round1_foundation` $\rightarrow$ **12/12 PASS** in 9.068s.
- **Complete GST App Suite**: `python manage.py test apps.gst` $\rightarrow$ **41/41 PASS** in 20.784s.
- **Accounting Regression Suite**: `python manage.py test apps.accounting.tests_upload_security apps.accounting.tests_stage4_13_stabilization` $\rightarrow$ **9/9 PASS** in 2.753s.
- **Frontend Test Suite**: `npm test --prefix frontend` $\rightarrow$ **45/45 PASS** in 1.26s.
- **Frontend TypeScript Check**: `cd frontend; npx tsc --noEmit` $\rightarrow$ **0 errors**.
- **Live Health Endpoint**: `https://vouch-u3u7.onrender.com/api/v1/health/environment/` $\rightarrow$ **HTTP 200, Commit 8adc8da2, Database neondb_staging**.

---

## 4. Owner Next Steps for Live Sandbox Activation

1. Log in to [developer.sandbox.co.in](https://developer.sandbox.co.in) and navigate to your application.
2. Ensure the **GST** product is enabled.
3. Open the Render Dashboard $\rightarrow$ **vouch-staging** (`vouch-u3u7`) $\rightarrow$ **Environment**.
4. Add the following environment variables:
   - `SANDBOX_API_KEY`: `<Your Sandbox API Key>`
   - `SANDBOX_API_SECRET`: `<Your Sandbox API Secret>`
   - `SANDBOX_BASE_URL`: `https://api.sandbox.co.in`
   - `GST_ENCRYPTION_KEY`: `<Your Base64 32-byte Fernet Key>`
5. In the Render Dashboard for `vouch-staging` (`vouch-u3u7`), trigger **Manual Deploy** $\rightarrow$ **Deploy latest commit**.
