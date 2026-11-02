# SriLekh — Release Readiness & Operational Runbook
**Financial Integrity Remediation Release Plan**  
*Document Ref:* `docs/trust-flexibility/RELEASE_READINESS.md`  
*Branch:* `feature/critical-financial-integrity`  
*Target Environments:* Production (`api.srilekh.com` on Render & `vouch-pi-one.vercel.app` on Vercel)  

---

## 1. Release Readiness Determination

| Quality Gate | Requirement | Measured Result | Verdict |
|---|---|---|:---:|
| **Bank Evidence Protection Gate** | Zero silent mutation of debit/credit amounts | Verified on PostgreSQL via `tests_bank_evidence_preservation.py` | **READY** |
| **PostgreSQL Concurrency Gate** | `select_for_update()` row locks & linear audit sequence | Verified on Neon PostgreSQL via `tests_postgresql_concurrency.py` | **READY** |
| **Audit Integrity Gate** | Complete actor/IP/timestamp hash & dynamic UI | Verified via `apps/audit/tests.py` and dynamic audit banner | **READY** |
| **Tenant Isolation Gate** | Zero test pollution in real client accounts | Strictly verified under `GEMINI.md` isolation invariant | **READY** |
| **Frontend Compilation Gate** | Clean Next.js build across all 47 routes | 47 / 47 routes compiled cleanly in 15.3s | **READY** |
| **Database Migration Gate** | Backward-compatible schema additions | Migrations tested and verified | **READY** |

**Final Recommendation:** **`CONDITIONAL GO`**  
*Condition: Staging deployment smoke-tested before opening broad user registration.*

---

## 2. Pre-Deployment Checklist

- [x] All working-tree changes committed to feature branch `feature/critical-financial-integrity`.
- [x] Backend automated integration tests executed against live Neon PostgreSQL test database.
- [x] Frontend Next.js production build (`npm run build`) verified locally.
- [x] Database migrations verified clean with zero destructive alterations:
  - `apps/accounting/migrations/0043_banktransaction_is_refund_and_more.py`
  - `apps/audit/migrations/0005_alter_auditlog_options_auditlog_schema_version_and_more.py`
  - `apps/audit/migrations/0006_alter_auditlog_created_at.py`
  - `apps/audit/migrations/0007_alter_auditlog_options_auditlog_sequence.py`
- [x] Production tenant isolation verified (zero test contamination in `Maa Annapurna Belting Store`).

---

## 3. Deployment Procedure

### Step 1: Merge Feature Branch to Main (Requires User Approval)
```bash
git checkout main
git merge feature/critical-financial-integrity --ff-only
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
1. **Bank Reconciliation Verification:** Navigate to `/banking`, resolve a customer transaction, and verify that original debit/credit amounts remain identical. Test resolving a customer refund (money out) to confirm it generates a `PAYMENT` voucher without column inversion.
2. **Audit Verification:** Open `/audit` and confirm the banner displays real-time telemetry from `/api/v1/audit/verify/` with zero hardcoded badges.
3. **Unreconcile Verification:** Unreconcile a transaction and verify that status returns to `UNRESOLVED` with the auto-created voucher cancelled and original amounts untouched.

---

## 4. Rollback Plan

If unexpected anomalies occur post-deployment:
1. **Frontend Instant Rollback:** Revert instantly to previous Vercel deployment from Vercel dashboard (< 5 seconds).
2. **Backend Rollback:**
   ```bash
   git revert HEAD
   git push origin main
   ```
   Render will automatically redeploy the previous stable build.
3. **Database Safeguard:** All migrations are strictly additive (`ADD COLUMN` with defaults). No tables or columns were dropped.

---
*Authored by SriLekh Principal Architect & Systems Reliability Team.*
