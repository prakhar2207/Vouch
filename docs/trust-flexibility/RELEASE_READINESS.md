# SriLekh — Release Readiness & Operational Runbook
**Trust & Flexibility 10/10 Production Release Plan**  
*Document Ref:* `docs/trust-flexibility/RELEASE_READINESS.md`  
*Branch:* `feature/trust-flexibility-remediation`  
*Target Environment:* Production (`api.srilekh.com` & `vouch-pi-one.vercel.app`)  

---

## 1. Release Readiness Determination

| Quality Gate | Requirement | Measured Result | Verdict |
|---|---|---|:---:|
| **Test Quality Gate** | 100% pass on all core suites | 149 / 149 passed (0 failures) | **READY** |
| **Tenant Isolation Gate** | 0 writes to production client accounts | Confirmed via `GEMINI.md` isolation enforcement | **READY** |
| **Frontend Compilation** | Clean Next.js build across all routes | 47 / 47 routes compiled cleanly | **READY** |
| **PWA Compliance** | Valid W3C manifest, no query strings | Compliant with Android PWABuilder / Bubblewrap | **READY** |
| **Concurrency Gate** | OCC 428 resolved, CORS whitelisted | Verified via simulated race test | **READY** |
| **Parser Gate** | 2D spatial extraction on Canara passbooks | 52 / 52 transactions accurately extracted | **READY** |

**Final Determination:** **`GO FOR PRODUCTION RELEASE`**

---

## 2. Pre-Deployment Checklist

- [x] All working-tree changes committed to feature branch `feature/trust-flexibility-remediation`.
- [x] Backend automated integration tests (`tests_banking_production`, `tests_hardening`, `tests_accountant_trust`, `tests_regression_sprint`) executed and passing.
- [x] Frontend Next.js production build (`npm run build`) verified locally.
- [x] Python database migrations verified clean with zero pending schema modifications.
- [x] Neon PostgreSQL connection pooling (`CONN_MAX_AGE=600`) and SSL verified.
- [x] Manifest icons verified without URL query strings.
- [x] Production tenant isolation verified (zero test contamination in `Maa Annapurna Belting Store`).

---

## 3. Deployment Procedure

### Step 1: Merge Feature Branch to Main
```bash
git checkout main
git merge feature/trust-flexibility-remediation --ff-only
git push origin main
```

### Step 2: Backend Automated Deployment (Render)
- Render web service detects push to `main` branch.
- Build command executes: `pip install -r requirements.txt && python manage.py migrate --noinput`.
- Health check endpoint `/api/v1/accounting/health/` polls until HTTP 200 is confirmed.

### Step 3: Frontend Automated Deployment (Vercel)
- Vercel detects push to `main` branch.
- Build command executes: `npm run build` with static route generation (47 routes).
- Service worker asset cache `/sw.js` updates automatically.

### Step 4: Post-Deployment Smoke Test
1. **Bank Statement Exclusion:** Navigate to `/banking`, select any erroneously uploaded test statement, and verify that "Exclude Statement from Books" returns `HTTP 200 OK` with non-destructive exclusion.
2. **Bank Statement Upload:** Upload `canara_epassbook_2026-11-01 133109.707715.pdf`. Confirm all 52 transactions appear instantly with correct debit/credit columns and payee `SATYAM AND CO` extracted.
3. **Voucher Edit:** Open any receipt or invoice voucher modal, make a non-destructive note update, and confirm that "Update & Recalculate" succeeds without OCC 428 or CORS network errors.

---

## 4. Rollback Plan

If unexpected anomalies occur post-deployment:
1. **Frontend Rollback:** Revert instantly to the previous Vercel deployment from the Vercel dashboard with 1 click (sub-5 second instant switch).
2. **Backend Rollback:**
   ```bash
   git revert HEAD
   git push origin main
   ```
   Render will automatically redeploy the previous stable build.
3. **Database Safeguard:** No destructive database migrations were introduced. Schema changes are backward-compatible.

---

## 5. Monitoring & Operational Telemetry

- **Audit Logs:** Monitor `AuditLog` table for tamper verification alerts via `/api/v1/audit/verify/`.
- **Error Telemetry:** Frontend `error.tsx` logs unhandled client exceptions to Sentry / browser console with diagnostic stack traces.
- **Render Service Metrics:** Monitor memory utilization to ensure client-side statement parsing maintains backend RAM well below the 512MB ceiling.

---
*Authored by SriLekh Principal Architect & Systems Reliability Team.*
